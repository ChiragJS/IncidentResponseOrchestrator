package executor

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/ChiragJS/IncidentResponseOrchestrator/pkg/logger"
	"go.uber.org/zap"
	v1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/util/homedir"
)

var Clientset *kubernetes.Clientset

func InitK8sClient() {
	var kubeconfig string
	if home := homedir.HomeDir(); home != "" {
		kubeconfig = filepath.Join(home, ".kube", "config")
	} else {
		kubeconfig = os.Getenv("KUBECONFIG")
	}

	// Try to build config from flags (local dev)
	config, err := clientcmd.BuildConfigFromFlags("", kubeconfig)
	if err != nil {
		// Fallback to in-cluster config (pod)
		config, err = rest.InClusterConfig()
		if err != nil {
			logger.Log.Warn("Failed to load kubeconfig (both local and in-cluster failed)", zap.Error(err))
			return
		}
	}

	Clientset, err = kubernetes.NewForConfig(config)
	if err != nil {
		logger.Log.Fatal("Failed to create k8s client", zap.Error(err))
	}
	logger.Log.Info("K8s client initialized successfully")
}

func RestartPod(target string, params map[string]string) error {
	// If target lacks "pod/" prefix and looks like a service/deployment name, prefer Rolling Restart
	if !strings.HasPrefix(target, "pod/") && !strings.Contains(target, "-") {
		// Heuristic: If it's just "kafka-ingest", it's likely a deployment.
		// But "kafka-ingest-123" is a pod.
		// Let's just try to get the pod, if fail, try rolling restart.
	}

	// Better logic:
	if Clientset == nil {
		logger.Log.Warn("SIMULATION MODE: ...")
		return nil
	}

	namespace := params["namespace"]
	if namespace == "" {
		namespace = "default"
	}

	// If explicit "deployment/" prefix or simple name that might be a deployment
	if strings.HasPrefix(target, "deployment/") {
		return RollingRestartDeployment(target, params)
	}

	podName := strings.TrimPrefix(target, "pod/")

	err := Clientset.CoreV1().Pods(namespace).Delete(context.TODO(), podName, v1.DeleteOptions{})
	if err != nil {
		// If failed to delete pod (e.g. not found), and it looks like a deployment name, try rolling restart
		if strings.Contains(err.Error(), "not found") {
			logger.Log.Info("Pod not found, attempting Rolling Restart of deployment", zap.String("target", target))
			return RollingRestartDeployment(target, params)
		}
		return err
	}
	return nil
}

func ScaleDeployment(target string, params map[string]string) error {
	if Clientset == nil {
		logger.Log.Warn("SIMULATION MODE: K8s client not available. Pretending to scale.",
			zap.String("target", target),
			zap.Any("params", params))
		time.Sleep(2 * time.Second)
		return nil
	}

	namespace := params["namespace"]
	if namespace == "" {
		namespace = "default"
	}
	deploymentName := strings.TrimPrefix(target, "deployment/")

	// 1. Get current deployment
	deploy, err := Clientset.AppsV1().Deployments(namespace).Get(context.TODO(), deploymentName, v1.GetOptions{})
	if err != nil {
		return err
	}

	// 2. Calculate new replicas
	currentReplicas := *deploy.Spec.Replicas
	var newReplicas int32

	if val, ok := params["replicas"]; ok {
		// Absolute value
		fmt.Sscanf(val, "%d", &newReplicas)
	} else if val, ok := params["replicas_increment"]; ok {
		var inc int32
		fmt.Sscanf(val, "%d", &inc)
		newReplicas = currentReplicas + inc
	} else if val, ok := params["replicas_increase"]; ok {
		var inc int32
		fmt.Sscanf(val, "%d", &inc)
		newReplicas = currentReplicas + inc
	} else {
		return fmt.Errorf("missing replicas, replicas_increment, or replicas_increase param")
	}

	logger.Log.Info("Scaling deployment",
		zap.String("deployment", deploymentName),
		zap.Int32("current", currentReplicas),
		zap.Int32("new", newReplicas))

	deploy.Spec.Replicas = &newReplicas

	// 3. Update
	_, err = Clientset.AppsV1().Deployments(namespace).Update(context.TODO(), deploy, v1.UpdateOptions{})
	return err
}

func RollingRestartDeployment(target string, params map[string]string) error {
	if Clientset == nil {
		logger.Log.Warn("SIMULATION MODE: K8s client not available. Pretending to rollout restart.",
			zap.String("target", target))
		time.Sleep(2 * time.Second)
		return nil
	}

	namespace := params["namespace"]
	if namespace == "" {
		namespace = "default"
	}
	deploymentName := strings.TrimPrefix(target, "deployment/")

	logger.Log.Info("Triggering rolling restart", zap.String("deployment", deploymentName))

	// Get deployment
	deploy, err := Clientset.AppsV1().Deployments(namespace).Get(context.TODO(), deploymentName, v1.GetOptions{})
	if err != nil {
		return err
	}

	// Update annotation to trigger rollout
	if deploy.Spec.Template.Annotations == nil {
		deploy.Spec.Template.Annotations = make(map[string]string)
	}
	deploy.Spec.Template.Annotations["kubectl.kubernetes.io/restartedAt"] = time.Now().Format(time.RFC3339)

	_, err = Clientset.AppsV1().Deployments(namespace).Update(context.TODO(), deploy, v1.UpdateOptions{})
	return err
}

// RollbackDeployment performs a rollback using kubectl rollout undo
func RollbackDeployment(target string, params map[string]string) error {
	deploymentName := strings.TrimPrefix(target, "deployment/")
	namespace := params["namespace"]
	if namespace == "" {
		namespace = "default"
	}

	logger.Log.Info("Attempting Rollback (kubectl rollout undo)",
		zap.String("deployment", deploymentName),
		zap.String("namespace", namespace))

	// Execute kubectl command
	cmd := exec.Command("kubectl", "rollout", "undo", "deployment/"+deploymentName, "-n", namespace)
	output, err := cmd.CombinedOutput()
	if err != nil {
		logger.Log.Error("Rollback failed", zap.String("output", string(output)), zap.Error(err))
		return fmt.Errorf("kubectl rollback failed: %s (%v)", string(output), err)
	}

	logger.Log.Info("Rollback successful", zap.String("output", string(output)))
	return nil
}
