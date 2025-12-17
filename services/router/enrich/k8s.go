package enrich

import (
	"context"
	"os"
	"path/filepath"

	"github.com/ChiragJS/IncidentResponseOrchestrator/pkg/events"
	"github.com/ChiragJS/IncidentResponseOrchestrator/pkg/logger"
	"go.uber.org/zap"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/util/homedir"
)

var clientset *kubernetes.Clientset

func InitK8sClient() {
	var kubeconfig string
	if home := homedir.HomeDir(); home != "" {
		kubeconfig = filepath.Join(home, ".kube", "config")
	} else {
		kubeconfig = os.Getenv("KUBECONFIG")
	}

	config, err := clientcmd.BuildConfigFromFlags("", kubeconfig)
	if err != nil {
		// Fallback to in-cluster config
		config, err = rest.InClusterConfig()
		if err != nil {
			logger.Log.Warn("K8s client init failed (enrichment will be limited)", zap.Error(err))
			return
		}
	}

	clientset, err = kubernetes.NewForConfig(config)
	if err != nil {
		logger.Log.Warn("K8s clientset creation failed", zap.Error(err))
		return
	}
	logger.Log.Info("K8s client initialized for Router enrichment")
}

func Enrich(ev *events.NormalizedEvent) *events.DomainEvent {
	// 1. Extract service name from payload
	serviceName := extractServiceName(ev)

	// 2. Determine domain
	domain := determineDomain(ev)

	// 3. Get cluster ID from env or default
	clusterID := os.Getenv("CLUSTER_ID")
	if clusterID == "" {
		clusterID = "default-cluster"
	}

	// 4. Query K8s for related resources
	relatedResources := getRelatedResources(serviceName)

	return &events.DomainEvent{
		EventId:          ev.EventId,
		Domain:           domain,
		ClusterId:        clusterID,
		ServiceName:      serviceName,
		RelatedResources: relatedResources,
		OriginalEvent:    ev,
	}
}

func extractServiceName(ev *events.NormalizedEvent) string {
	if ev.RawPayload != nil {
		if fields := ev.RawPayload.GetFields(); fields != nil {
			// Try "service_name" first
			if val, ok := fields["service_name"]; ok {
				return val.GetStringValue()
			}
			// Fallback to "service"
			if val, ok := fields["service"]; ok {
				return val.GetStringValue()
			}
			// Try inside "commonLabels" struct (AlertManager webhook format)
			if commonLabelsVal, ok := fields["commonLabels"]; ok {
				if commonLabelsStruct := commonLabelsVal.GetStructValue(); commonLabelsStruct != nil {
					commonLabelsFields := commonLabelsStruct.GetFields()
					// Try "pod" in commonLabels
					if val, ok := commonLabelsFields["pod"]; ok {
						return val.GetStringValue()
					}
				}
			}
			// Try inside "labels" struct (from AlertManager)
			if labelsVal, ok := fields["labels"]; ok {
				if labelsStruct := labelsVal.GetStructValue(); labelsStruct != nil {
					labelsFields := labelsStruct.GetFields()
					// Try "pod" in labels (AlertManager format)
					if val, ok := labelsFields["pod"]; ok {
						return val.GetStringValue()
					}
					// Try "service" in labels
					if val, ok := labelsFields["service"]; ok {
						return val.GetStringValue()
					}
				}
			}
			// Try inside "metadata" struct (from ingest API)
			if metaVal, ok := fields["metadata"]; ok {
				if metaStruct := metaVal.GetStructValue(); metaStruct != nil {
					metaFields := metaStruct.GetFields()
					// Try "service" inside metadata
					if val, ok := metaFields["service"]; ok {
						return val.GetStringValue()
					}
					// Try "pod" as fallback
					if val, ok := metaFields["pod"]; ok {
						return val.GetStringValue()
					}
				}
			}
		}
	}
	return "unknown-service"
}

func determineDomain(ev *events.NormalizedEvent) string {
	if ev.RawPayload != nil {
		if fields := ev.RawPayload.GetFields(); fields != nil {
			// Check source for domain hints
			if srcVal, ok := fields["source"]; ok {
				src := srcVal.GetStringValue()
				if src == "kubernetes" || src == "k8s" {
					return "k8s"
				}
				if src == "postgres" || src == "mysql" || src == "mongodb" {
					return "db"
				}
			}
			// Check alert name for hints
			if alertVal, ok := fields["alert"]; ok {
				alert := alertVal.GetStringValue()
				if contains(alert, "Kafka", "Consumer", "Topic") {
					return "infra"
				}
				if contains(alert, "Pod", "Node", "Deployment") {
					return "k8s"
				}
			}
		}
	}
	return "infra" // Default
}

func contains(s string, substrs ...string) bool {
	for _, sub := range substrs {
		if len(sub) > 0 && len(s) >= len(sub) {
			for i := 0; i <= len(s)-len(sub); i++ {
				if s[i:i+len(sub)] == sub {
					return true
				}
			}
		}
	}
	return false
}

func getRelatedResources(serviceName string) []string {
	if clientset == nil || serviceName == "unknown-service" {
		return []string{}
	}

	var resources []string
	namespace := "default"

	// Try to find deployment
	deployments, err := clientset.AppsV1().Deployments(namespace).List(context.TODO(), metav1.ListOptions{})
	if err == nil {
		for _, dep := range deployments.Items {
			if dep.Name == serviceName {
				resources = append(resources, "deployment/"+dep.Name)
				// Get pods for this deployment
				pods, _ := clientset.CoreV1().Pods(namespace).List(context.TODO(), metav1.ListOptions{
					LabelSelector: "app=" + serviceName,
				})
				for _, pod := range pods.Items {
					resources = append(resources, "pod/"+pod.Name)
				}
				break
			}
		}
	}

	return resources
}
