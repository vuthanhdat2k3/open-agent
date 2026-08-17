FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
ARG API_INTERNAL_URL=http://api:8000
ARG NEXT_PUBLIC_AUTH_PROVIDER=local
ENV API_INTERNAL_URL=$API_INTERNAL_URL
ENV NEXT_PUBLIC_AUTH_PROVIDER=$NEXT_PUBLIC_AUTH_PROVIDER
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV API_INTERNAL_URL=http://api:8000
COPY --from=builder /app ./
EXPOSE 3000
CMD ["npm", "run", "start"]
