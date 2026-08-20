# syntax=docker/dockerfile:1

# --- Étape 1 : build du widget (un seul fichier IIFE) ---
FROM node:20-alpine AS builder

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build          # -> dist/skapa-widget.js

# --- Étape 2 : service statique ---
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80
