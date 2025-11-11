pipeline {
  agent any
  stages {
    stage('Build Docker Image') {
      steps {
        script {
          // Dockerfileがある場所で
          docker.build('chat:latest', '.')
        }
      }
    }
  }
}
