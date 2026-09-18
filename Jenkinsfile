pipeline {
  agent any
  stages {
    stage('Build Docker Image') {
      steps {
        script {
          // Build context is the repo root; the Dockerfile lives in aws/
          docker.build('chat:latest', '-f aws/Dockerfile.production .')
        }
      }
    }
  }
}
