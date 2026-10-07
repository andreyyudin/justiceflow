import {
  User,
  UserManager,
  WebStorageStateStore,
  type UserManagerSettings,
} from "oidc-client-ts";

const authority =
  process.env.NEXT_PUBLIC_OIDC_AUTHORITY ??
  "http://localhost:8080/realms/justiceflow";
const clientId =
  process.env.NEXT_PUBLIC_OIDC_CLIENT_ID ?? "justiceflow-web";
const audience =
  process.env.NEXT_PUBLIC_OIDC_AUDIENCE ?? "justiceflow-api";

export function createUserManager(): UserManager {
  const settings: UserManagerSettings = {
    authority,
    client_id: clientId,
    redirect_uri: window.location.origin,
    post_logout_redirect_uri: window.location.origin,
    response_type: "code",
    scope: "openid profile",
    extraQueryParams: {
      audience,
    },
    automaticSilentRenew: true,
    userStore: new WebStorageStateStore({
      store: window.sessionStorage,
    }),
  };

  return new UserManager(settings);
}

export async function loadAuthenticatedUser(
  manager: UserManager,
): Promise<User | null> {
  const callback = new URL(window.location.href);
  if (callback.searchParams.has("code") && callback.searchParams.has("state")) {
    const user = await manager.signinCallback();
    window.history.replaceState({}, document.title, window.location.pathname);
    return user ?? null;
  }

  return manager.getUser();
}

export function bearerHeaders(
  accessToken: string,
  includeJson = false,
): HeadersInit {
  return {
    Authorization: `Bearer ${accessToken}`,
    ...(includeJson ? { "Content-Type": "application/json" } : {}),
  };
}
