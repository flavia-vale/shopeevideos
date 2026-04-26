# Usa a imagem oficial do Playwright com Python já preparada
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Instala dependências do sistema necessárias para o build do frontend (Node.js)
RUN apt-get update && apt-get install -y curl
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y nodejs

# Copia arquivos de dependências primeiro
COPY package.json requirements.txt ./

# Instala dependências Python e Node.js
RUN pip install --no-cache-dir -r requirements.txt
RUN npm install

# Instala os navegadores do Playwright necessários
RUN playwright install chromium

# Copia o restante dos arquivos do projeto
COPY . .

# Build do frontend React
RUN npm run build

# Expõe a porta que o Render usará
EXPOSE 10000

# Comando para executar o servidor principal
CMD ["python", "main.py"]