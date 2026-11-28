FROM node:22-alpine@sha256:1314fb30ec37592d5845e5a160d522c0e680972aa534549940b8d73bde88481a AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=http://localhost:8000/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build
FROM nginx/nginx-unprivileged:1.31.10-alpine3.24-slim@sha256:f4afc48254dc77ea692ec6979d220e5b1176331c636a4d51c502ffdded6789bd
USER root
RUN apk add --no-cache 'zlib=1.4-r0'
USER 101
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 8080
