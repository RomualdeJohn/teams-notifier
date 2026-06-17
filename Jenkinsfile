#!/bin/groovy

@Library('cpd-workflowlibs@master') _

pipeline {
    agent {
        kubernetes {
            inheritFrom "jenkins-buildah-agent"
        }
    }

    options {
        timestamps()
        ansiColor('xterm')
    }

    parameters {
        string(name: 'IMAGE_TAG', defaultValue: '', description: 'Optional image tag (defaults to BUILD_TIMESTAMP)')
    }

    environment {
        APP_NAME = 'sagt-teams-notification'
        MANIFEST_FILE = 'resource.yaml'
        PROJECT_NAME = "oss-operation-cronjobs"
        REGISTRY_URL = "registry-jpe1.r-local.net"
        K8S_CLUSTER_ID = "jpe1-caas1-dev5"
        K8S_NAMESPACE = "oss-operation-cronjobs"
        FULL_IMAGE_NAME = "${REGISTRY_URL}/${PROJECT_NAME}/${APP_NAME}"
        IMAGE_TAG = "${params.IMAGE_TAG ?: BUILD_TIMESTAMP}"
    }

    stages {

        stage('Debug Environment') {
            steps {
                sh 'printenv | sort'
            }
        }

        stage('Run Tests') {
            steps {
                script {
                    echo "Installing dependencies and running tests..."
                    sh '''
                        # Try to create virtual environment, fallback to --break-system-packages if needed
                        if python3 -m venv venv 2>/dev/null; then
                            echo "Using virtual environment approach..."
                            . venv/bin/activate
                            pip install --upgrade pip
                            pip install -r requirements.txt
                        else
                            echo "Virtual environment not available, using --break-system-packages..."
                            pip install --break-system-packages -r requirements.txt
                        fi
                        
                        # Run tests with coverage and JUnit XML output
                        python -m pytest test/ -v --tb=short --cov=app --cov-report=term-missing --junitxml=test-results.xml
                    '''
                }
            }
            post {
                always {
                    // Publish test results and archive artifacts (if they exist)
                    script {
                        if (fileExists('test-results.xml')) {
                            junit 'test-results.xml'
                            archiveArtifacts artifacts: 'test-results.xml', allowEmptyArchive: true
                        } else {
                            echo 'No test results file found to publish'
                        }
                    }
                    // Clean up virtual environment
                    sh 'rm -rf venv || true'
                }
                failure {
                    echo 'Tests failed! Build will not proceed.'
                }
            }
        }

        stage('Build Image') {
            steps {
                container('buildah') {
                    script {
                        echo "Logging in into registry..."
                        withCredentials([usernamePassword(credentialsId: "jpe1-harbor-bot", usernameVariable: 'USERNAME', passwordVariable: 'PASSWORD')]) {
                            sh 'buildah login --username $USERNAME --password $PASSWORD $REGISTRY_URL'
                        }

                        echo "Building image..."
                        sh """
                            buildah bud \
                            -f "${WORKSPACE}/Dockerfile" \
                            -t "${FULL_IMAGE_NAME}:latest" \
                            "${WORKSPACE}"
                        """

                        echo "Tagging image with ${IMAGE_TAG}..."
                        sh "buildah tag ${FULL_IMAGE_NAME}:latest ${FULL_IMAGE_NAME}:${IMAGE_TAG}"

                        echo "Pushing image with tag ${IMAGE_TAG}..."
                        sh "buildah push ${FULL_IMAGE_NAME}:${IMAGE_TAG}"
                    }
                }
            }
        }

        stage('Build Kubernetes Manifest') {
            steps {
                dir("k8s-config") {
                    sh label: 'Update image tag in kustomization', script: """
                        sed -i.bak 's/newTag: latest/newTag: "${IMAGE_TAG}"/' kustomization.yaml
                    """
                    sh label: 'Generate resource.yaml with kustomize', script: """
                        kubectl kustomize . > ${WORKSPACE}/${MANIFEST_FILE}
                    """
                }
            }
            post {
                success {
                    archiveArtifacts artifacts: MANIFEST_FILE, fingerprint: true
                }
            }
        }

        stage('Apply Manifests') {
            steps {
                script {
                    echo "Applying manifest: ${MANIFEST_FILE}"
                    cpd.kubectl("apply -f ${MANIFEST_FILE}")
                }
            }
        }
    }

    post {
        success {
            echo 'Pipeline succeeded!'
        }
        unstable {
            echo 'Pipeline is unstable.'
        }
        failure {
            echo 'Pipeline failed.'
        }
        changed {
            echo 'Pipeline result changed.'
        }
        always {
            script {
                currentBuild.result = currentBuild.currentResult
            }
        }
    }
}
