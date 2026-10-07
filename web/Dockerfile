FROM node:22.23.3-bookworm-slim AS dependencies

WORKDIR /app

COPY package.json package-lock.json .npmrc ./
RUN npm install --global npm@12.2.0 \
    && npm ci


FROM node:22.23.3-bookworm-slim AS builder

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN mkdir -p /app/public

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_OIDC_AUTHORITY=http://localhost:8080/realms/justiceflow
ARG NEXT_PUBLIC_OIDC_CLIENT_ID=justiceflow-web
ARG NEXT_PUBLIC_OIDC_AUDIENCE=justiceflow-api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_OIDC_AUTHORITY=$NEXT_PUBLIC_OIDC_AUTHORITY
ENV NEXT_PUBLIC_OIDC_CLIENT_ID=$NEXT_PUBLIC_OIDC_CLIENT_ID
ENV NEXT_PUBLIC_OIDC_AUDIENCE=$NEXT_PUBLIC_OIDC_AUDIENCE

RUN npm run build


FROM node:22.23.3-bookworm-slim AS runtime

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

RUN apt-get update \
    && apt-get install --only-upgrade --no-install-recommends -y perl-base \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /usr/local/lib/node_modules/npm \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx \
    && groupadd --system --gid 1001 nodejs \
    && useradd --system --uid 1001 --gid nodejs nextjs

COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
