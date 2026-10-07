const ROLE_CLAIM = "https://justiceflow.example/roles";
const ALLOWED_ROLES = new Set(["caseworker", "auditor"]);

exports.onExecutePostLogin = async (event, api) => {
  const role = event.user.app_metadata?.justiceflow_role;
  const displayName = event.user.name || event.user.nickname;

  if (!ALLOWED_ROLES.has(role)) {
    api.access.deny("A JusticeFlow caseworker or auditor role is required.");
    return;
  }

  if (typeof displayName !== "string" || !displayName.trim()) {
    api.access.deny("A JusticeFlow display identity is required.");
    return;
  }

  api.accessToken.setCustomClaim(ROLE_CLAIM, [role]);
  api.accessToken.setCustomClaim("name", displayName);
};
