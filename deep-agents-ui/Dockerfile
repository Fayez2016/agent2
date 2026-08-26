FROM node:20-alpine AS builder
WORKDIR /app

# Enable corepack for yarn
RUN corepack enable

COPY package.json yarn.lock* ./
RUN yarn install --frozen-lockfile || yarn install

COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN yarn build || npm run build

FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000

COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next

EXPOSE 3000
CMD ["npm", "start"]
