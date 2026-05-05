// Jenkins Pipeline: Build splitter image + (опционально) запуск K8s Job
//
// Parameters:
//   RUN_SPLITTER  — checkbox: запустить K8s Job после сборки (default: false)
//   FRAME_MODE    — rare | frequent (default: rare)
//   ONLY_KEYS     — фильтр файлов (comma-separated basename, пусто = все новые)
//   OUTPUT_PREFIX — MinIO output prefix (default: video/splitter_output)
//
// Fallback: если K8s Job не удался — Jenkins предлагает SSH-запуск (вариант A).

pipeline {
    agent none
    environment {
        REGISTRY     = 'registry.multiagent.vision'
        IMAGE_PREFIX = 'chessverse'
        SERVICE      = 'splitter'
        NAMESPACE    = 'chessverse'
    }
    parameters {
        booleanParam(name: 'RUN_SPLITTER',  defaultValue: false, description: 'Запустить K8s Job после сборки')
        choice(name:  'FRAME_MODE',         choices: ['rare', 'frequent'], description: 'Режим извлечения кадров')
        string(name:  'ONLY_KEYS',          defaultValue: '', description: 'Фильтр MinIO ключей (comma-separated basename), пусто = все новые')
        string(name:  'OUTPUT_PREFIX',      defaultValue: 'video/splitter_output', description: 'MinIO output prefix')
    }
    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }
    stages {
        stage('Checkout') {
            agent any
            steps {
                checkout scm
                script {
                    def sha = env.GIT_COMMIT?.take(7) ?: 'latest'
                    currentBuild.displayName = "#${env.BUILD_NUMBER} - sha-${sha}"
                    currentBuild.description = "${REGISTRY}/${IMAGE_PREFIX}/${SERVICE}:sha-${sha}"
                    stash name: 'workspace', includes: '**'
                    env.IMAGE_TAG = "sha-${sha}"
                }
            }
        }

        stage('Build and Push') {
            agent {
                kubernetes {
                    defaultContainer 'kaniko'
                    yaml """
apiVersion: v1
kind: Pod
spec:
  hostAliases:
  - hostnames: [registry.multiagent.vision]
    ip: 10.0.0.201
  containers:
  - name: kaniko
    image: gcr.io/kaniko-project/executor:v1.22.0-debug
    command: ["/busybox/cat"]
    tty: true
    volumeMounts:
    - name: docker-config
      mountPath: /kaniko/.docker
  volumes:
  - name: docker-config
    secret:
      secretName: harbor-credentials
      items:
      - key: .dockerconfigjson
        path: config.json
"""
                }
            }
            steps {
                unstash 'workspace'
                script {
                    def tag = env.IMAGE_TAG ?: "sha-${env.GIT_COMMIT?.take(7) ?: 'latest'}"
                    def maxRetries = 3
                    def kanikoExit = 1
                    for (int attempt = 1; attempt <= maxRetries; attempt++) {
                        echo "Kaniko attempt ${attempt}/${maxRetries}"
                        kanikoExit = sh(
                            script: """
                                /kaniko/executor \\
                                    --context \$(pwd) \\
                                    --dockerfile \$(pwd)/Dockerfile \\
                                    --build-arg GIT_SHA=${tag} \\
                                    --destination ${REGISTRY}/${IMAGE_PREFIX}/${SERVICE}:${tag} \\
                                    --destination ${REGISTRY}/${IMAGE_PREFIX}/${SERVICE}:latest \\
                                    --skip-tls-verify \\
                                    --cache=true
                            """,
                            returnStatus: true
                        )
                        if (kanikoExit == 0) break
                        if (attempt < maxRetries) {
                            echo "Kaniko failed (exit ${kanikoExit}), retrying in 30s..."
                            sleep(time: 30, unit: 'SECONDS')
                        }
                    }
                    if (kanikoExit != 0) {
                        error("Kaniko failed with exit code ${kanikoExit} after ${maxRetries} attempts.")
                    }
                    echo "Image pushed: ${REGISTRY}/${IMAGE_PREFIX}/${SERVICE}:${tag}"
                }
            }
        }

        // ── Вариант W: Windows agent (D3D11VA hardware HEVC decoder) ──────────
        stage('Run Splitter (Windows — HEVC)') {
            when {
                allOf {
                    expression { return params.RUN_SPLITTER == true }
                    expression {
                        def keys = params.ONLY_KEYS?.toLowerCase() ?: ''
                        return keys.contains('.h265') || keys.contains('.hevc')
                    }
                }
            }
            agent { label 'windows-hevc' }
            steps {
                unstash 'workspace'
                script {
                    def onlyArg = params.ONLY_KEYS?.trim() ?: ''
                    def outPrefix = params.OUTPUT_PREFIX?.trim() ?: 'video/splitter_output'
                    withCredentials([
                        usernamePassword(
                            credentialsId: 'splitter-minio-creds',
                            usernameVariable: 'AWS_ACCESS_KEY_ID',
                            passwordVariable: 'AWS_SECRET_ACCESS_KEY'
                        )
                    ]) {
                        withEnv([
                            "FRAME_MODE=${params.FRAME_MODE}",
                            "QUALITY_LEVEL=low",
                            "MINIO_OUTPUT_PREFIX=${outPrefix}",
                            "ONLY_KEYS=${onlyArg}"
                        ]) {
                            bat "pip install -q -r requirements.txt && python minio_worker.py --once --no-progress"
                        }
                    }
                }
            }
        }

        // ── Вариант B: K8s Job (для не-HEVC форматов) ─────────────────────────
        stage('Deploy K8s Job') {
            when {
                allOf {
                    expression { return params.RUN_SPLITTER == true }
                    expression {
                        def keys = params.ONLY_KEYS?.toLowerCase() ?: ''
                        return !keys.contains('.h265') && !keys.contains('.hevc')
                    }
                }
            }
            agent {
                kubernetes {
                    defaultContainer 'kubectl'
                    yaml """
apiVersion: v1
kind: Pod
spec:
  serviceAccountName: jenkins-deployer
  containers:
  - name: kubectl
    image: alpine/k8s:1.28.3
    command: ["/bin/sh", "-c", "sleep infinity"]
    tty: true
"""
                }
            }
            steps {
                script {
                    def tag    = env.IMAGE_TAG ?: "latest"
                    def ts     = new Date().format("yyyyMMdd-HHmm")
                    def jobName = "splitter-${params.FRAME_MODE}-${ts}"
                    def onlyArg = params.ONLY_KEYS?.trim() ? "--only=${params.ONLY_KEYS.trim()}" : ""

                    // Генерируем Job manifest на лету
                    writeFile file: 'splitter-job-run.yaml', text: """
apiVersion: batch/v1
kind: Job
metadata:
  name: ${jobName}
  namespace: ${NAMESPACE}
  labels:
    app: splitter
    frame-mode: ${params.FRAME_MODE}
spec:
  ttlSecondsAfterFinished: 86400
  backoffLimit: 1
  template:
    metadata:
      labels:
        app: splitter
    spec:
      restartPolicy: Never
      imagePullSecrets:
        - name: harbor-pull
      containers:
        - name: splitter
          image: ${REGISTRY}/${IMAGE_PREFIX}/${SERVICE}:${tag}
          imagePullPolicy: Always
          command: ["python", "minio_worker.py", "--once", "${onlyArg}"]
          env:
            - name: FRAME_MODE
              value: "${params.FRAME_MODE}"
            - name: QUALITY_LEVEL
              value: "low"
            - name: SPLITER_WORK_DIR
              value: "/data/work"
            - name: MINIO_OUTPUT_PREFIX
              value: "${params.OUTPUT_PREFIX}"
            - name: LOG_LEVEL
              value: "DEBUG"
          envFrom:
            - secretRef:
                name: splitter-minio-credentials
            - secretRef:
                name: splitter-cf-access
          volumeMounts:
            - name: work
              mountPath: /data/work
            - name: config
              mountPath: /app/config.json
              subPath: config.json
          resources:
            requests:
              cpu: "2"
              memory: "4Gi"
            limits:
              cpu: "4"
              memory: "8Gi"
      volumes:
        - name: work
          emptyDir:
            sizeLimit: 30Gi
        - name: config
          configMap:
            name: splitter-config
"""
                    sh "kubectl apply -f splitter-job-run.yaml"
                    echo "K8s Job создан: ${jobName}"

                    // Ожидаем завершения (до 4 часов)
                    def waitResult = sh(
                        script: "kubectl wait --for=condition=complete --timeout=14400s job/${jobName} -n ${NAMESPACE}",
                        returnStatus: true
                    )
                    // Всегда собираем логи пода (и при успехе и при ошибке)
                    echo "=== K8s Pod Logs ==="
                    sh "kubectl logs -n ${NAMESPACE} --selector=job-name=${jobName} --tail=500 || true"
                    echo "=== End of Pod Logs ==="

                    if (waitResult != 0) {
                        error("K8s Job ${jobName} не завершился успешно. См. логи выше.")
                    }
                    echo "K8s Job ${jobName} завершён успешно."
                }
            }
        }
    }

    post {
        success {
            script {
                def tag = env.IMAGE_TAG ?: 'latest'
                echo "=== SUCCESS === Image: ${REGISTRY}/${IMAGE_PREFIX}/${SERVICE}:${tag}"
                if (params.RUN_SPLITTER) {
                    echo "Результаты в MinIO: ${params.OUTPUT_PREFIX}/"
                }
            }
        }
        failure {
            script {
                if (params.RUN_SPLITTER) {
                    echo """
=== FALLBACK Вариант A (SSH) ===
Если K8s Job не удался, запусти вручную на сервере:
  ssh user@<server> "docker run --rm \\
    -e FRAME_MODE=${params.FRAME_MODE} \\
    -e QUALITY_LEVEL=low \\
    -e SPLITER_WORK_DIR=/data/work \\
    -e AWS_ACCESS_KEY_ID=<key> \\
    -e AWS_SECRET_ACCESS_KEY=<secret> \\
    -e CF_ACCESS_CLIENT_ID=<cf_id> \\
    -e CF_ACCESS_CLIENT_SECRET=<cf_secret> \\
    -v /data/splitter-work:/data/work \\
    ${REGISTRY}/${IMAGE_PREFIX}/${SERVICE}:${env.IMAGE_TAG ?: 'latest'} \\
    python minio_worker.py --once"
"""
                }
            }
        }
    }
}
