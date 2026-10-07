const ROLE_CLAIM = "https://justiceflow.example/roles";
const ALLOWED_ROLES = new Set(["caseworker", "auditor"]);

exports.onExecutePostLogin = async (event, api) => {
  const role = event.user.app_metadata?.justiceflow_role;

  if (!ALLOWED_ROLES.has(role)) {
    api.access.deny("A JusticeFlow caseworker or auditor role is required.");
    return;
  }

  api.accessToken.setCustomClaim(ROLE_CLAIM, [role]);
};
