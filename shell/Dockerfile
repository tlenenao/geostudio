FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Build-time public config; override at build with --build-arg as needed.
ARG VITE_CORE_URL=http://localhost:8200
ARG VITE_OIDC_AUTHORITY=http://localhost:8180/realms/gis-platform
ARG VITE_OIDC_CLIENT_ID=shell
ARG VITE_OIDC_REDIRECT_URI=http://localhost:8300/
ENV VITE_CORE_URL=$VITE_CORE_URL \
    VITE_OIDC_AUTHORITY=$VITE_OIDC_AUTHORITY \
    VITE_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID \
    VITE_OIDC_REDIRECT_URI=$VITE_OIDC_REDIRECT_URI
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8300
