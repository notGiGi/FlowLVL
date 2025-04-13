FROM node:18-alpine as build

WORKDIR /app

# Copiar solo package.json (sin requerir package-lock.json)
COPY package.json ./

# Instalar dependencias
RUN npm install

# Copiar código fuente
COPY . .

# Construir la aplicación
RUN npm run build

# Imagen para producción
FROM nginx:alpine

# Copiar archivos estáticos desde la etapa de construcción
COPY --from=build /app/build /usr/share/nginx/html

# Copiar configuración de nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Exponer puerto
EXPOSE 80

# Iniciar nginx
CMD ["nginx", "-g", "daemon off;"]
