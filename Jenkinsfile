// Jenkins Pipeline: Build splitter Docker image and push to Harbor
// Trigger: push to main branch or manual build
// Image: registry.multiagent.vision/chessverse/splitter:sha-<commit_sha>

pipeline {
    agent none
    environment {
        REGISTRY     = 'registry.multiagent.vision'
        IMAGE_PREFIX = 'chessverse'
        SERVICE      = 'splitter'
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
                    currentBuild.description = "registry.multiagent.vision/chessverse/splitter:sha-${sha}"
                    stash name: 'workspace', includes: '**'
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
                    def sha = env.GIT_COMMIT?.take(7) ?: 'latest'
                    def tag = "sha-${sha}"
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
                }
            }
        }
    }
    post {
        success {
            script {
                def sha = env.GIT_COMMIT?.take(7) ?: 'latest'
                echo "Image pushed: ${REGISTRY}/${IMAGE_PREFIX}/${SERVICE}:sha-${sha}"
            }
        }
    }
}
