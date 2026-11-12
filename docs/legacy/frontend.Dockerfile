FROM node:20-alpine

WORKDIR /app

# Instalación reproducible a partir de package-lock.json
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
