type AccessRule = Record<string, unknown>;

interface AccessApplication {
  id: string;
  name: string;
  domain: string;
}

interface AccessGroup {
  id: string;
  name: string;
  include: AccessRule[];
  require: AccessRule[];
  exclude: AccessRule[];
}

interface AccessPolicy {
  id: string;
  name: string;
  decision: string;
  precedence: number;
  include: AccessRule[];
  require: AccessRule[];
  exclude: AccessRule[];
  session_duration?: string;
}

interface CloudflareEnvelope<T> {
  success: boolean;
  result: T;
  errors?: Array<{ message?: string }>;
}

const CLOUD_DOMAIN = "cloud-hub.inas-technologies.com/api/*";
const LOCAL_DOMAIN = "hub.inas-technologies.com";
const CLOUD_GROUP_NAME = "inas-cloud-hub-users";
const LOCAL_GROUP_NAME = "inas-local-hub-operators";
const LEGACY_GROUP_NAME = "inas-hub-allowed-users";

async function separateAccessGroups(
  client: CloudflareApi,
  mutate: boolean,
): Promise<Record<string, unknown>> {
  const apps = await client.get<AccessApplication[]>("/access/apps");
  const cloudApp = exactApp(apps, CLOUD_DOMAIN);
  const localApp = exactApp(apps, LOCAL_DOMAIN);
  const [groups, cloudPolicies, localPolicies] = await Promise.all([
    client.get<AccessGroup[]>("/access/groups"),
    client.get<AccessPolicy[]>(`/access/apps/${cloudApp.id}/policies`),
    client.get<AccessPolicy[]>(`/access/apps/${localApp.id}/policies`),
  ]);
  const cloudPolicy = oneAllowPolicy(cloudPolicies, cloudApp.name);
  const localPolicy = oneAllowPolicy(localPolicies, localApp.name);
  const localGroupId = oneGroupReference(localPolicy, localApp.name);
  let localGroup = requiredGroup(groups, localGroupId);
  let cloudGroup = groups.find((group) => group.name === CLOUD_GROUP_NAME) ?? null;
  if (cloudGroup?.id === localGroup.id) {
    throw new Error("Cloud Hub and Local Hub group IDs must be different");
  }

  const actions: string[] = [];
  if (!cloudGroup) {
    actions.push(`create ${CLOUD_GROUP_NAME} from the current Local Hub rules`);
  }
  if (localGroup.name !== LOCAL_GROUP_NAME) {
    if (localGroup.name !== LEGACY_GROUP_NAME) {
      throw new Error(
        `Refusing to rename unexpected Local Hub Access group: ${localGroup.name}`,
      );
    }
    actions.push(`rename ${LEGACY_GROUP_NAME} to ${LOCAL_GROUP_NAME}`);
  }
  if (!cloudGroup || !policyUsesOnlyGroup(cloudPolicy, cloudGroup.id)) {
    actions.push(`bind the Cloud Hub allow policy only to ${CLOUD_GROUP_NAME}`);
  }

  if (!mutate) {
    return {
      status: actions.length === 0 ? "already_separated" : "planned",
      cloud_app: cloudApp.name,
      local_app: localApp.name,
      actions,
    };
  }

  if (!cloudGroup) {
    cloudGroup = await client.post<AccessGroup>("/access/groups", {
      name: CLOUD_GROUP_NAME,
      include: localGroup.include,
      require: localGroup.require,
      exclude: localGroup.exclude,
    });
  }
  if (localGroup.name !== LOCAL_GROUP_NAME) {
    localGroup = await client.put<AccessGroup>(`/access/groups/${localGroup.id}`, {
      name: LOCAL_GROUP_NAME,
      include: localGroup.include,
      require: localGroup.require,
      exclude: localGroup.exclude,
    });
  }
  if (!policyUsesOnlyGroup(cloudPolicy, cloudGroup.id)) {
    await client.put<AccessPolicy>(
      `/access/apps/${cloudApp.id}/policies/${cloudPolicy.id}`,
      policyBody(cloudPolicy, cloudGroup.id),
    );
  }

  const [verifiedGroups, verifiedCloudPolicies, verifiedLocalPolicies] = await Promise.all([
    client.get<AccessGroup[]>("/access/groups"),
    client.get<AccessPolicy[]>(`/access/apps/${cloudApp.id}/policies`),
    client.get<AccessPolicy[]>(`/access/apps/${localApp.id}/policies`),
  ]);
  const verifiedCloudGroup = verifiedGroups.find((group) => group.name === CLOUD_GROUP_NAME);
  const verifiedLocalGroup = verifiedGroups.find((group) => group.name === LOCAL_GROUP_NAME);
  if (
    !verifiedCloudGroup ||
    !verifiedLocalGroup ||
    verifiedCloudGroup.id === verifiedLocalGroup.id
  ) {
    throw new Error("Access group separation verification failed");
  }
  const verifiedCloudPolicy = oneAllowPolicy(verifiedCloudPolicies, cloudApp.name);
  const verifiedLocalPolicy = oneAllowPolicy(verifiedLocalPolicies, localApp.name);
  if (
    !policyUsesOnlyGroup(verifiedCloudPolicy, verifiedCloudGroup.id) ||
    !policyUsesOnlyGroup(verifiedLocalPolicy, verifiedLocalGroup.id)
  ) {
    throw new Error("Access policy separation verification failed");
  }

  return {
    status: "separated",
    cloud: {
      application: cloudApp.name,
      group: verifiedCloudGroup.name,
      group_id: verifiedCloudGroup.id,
    },
    local: {
      application: localApp.name,
      group: verifiedLocalGroup.name,
      group_id: verifiedLocalGroup.id,
    },
    shared_group: false,
  };
}

function exactApp(apps: AccessApplication[], domain: string): AccessApplication {
  const matches = apps.filter((app) => app.domain === domain);
  if (matches.length !== 1) {
    throw new Error(`Expected exactly one Access application for ${domain}`);
  }
  return matches[0];
}

function oneAllowPolicy(policies: AccessPolicy[], appName: string): AccessPolicy {
  const matches = policies.filter((policy) => policy.decision === "allow");
  if (matches.length !== 1) {
    throw new Error(`Expected exactly one Allow policy on ${appName}`);
  }
  return matches[0];
}

function oneGroupReference(policy: AccessPolicy, appName: string): string {
  const ids = policy.include.flatMap((rule) => {
    const group = record(rule.group);
    return typeof group?.id === "string" ? [group.id] : [];
  });
  if (ids.length !== 1 || policy.include.length !== 1) {
    throw new Error(`Expected ${appName} Allow policy to contain exactly one Access group`);
  }
  return ids[0];
}

function requiredGroup(groups: AccessGroup[], id: string): AccessGroup {
  const group = groups.find((candidate) => candidate.id === id);
  if (!group) {
    throw new Error("The Local Hub Access group was not found");
  }
  return group;
}

function policyUsesOnlyGroup(policy: AccessPolicy, groupId: string): boolean {
  return (
    policy.include.length === 1 &&
    record(policy.include[0]?.group)?.id === groupId
  );
}

function policyBody(policy: AccessPolicy, groupId: string): Record<string, unknown> {
  return {
    name: policy.name,
    decision: policy.decision,
    precedence: policy.precedence,
    include: [{ group: { id: groupId } }],
    require: policy.require,
    exclude: policy.exclude,
    ...(policy.session_duration ? { session_duration: policy.session_duration } : {}),
  };
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim() ?? "";
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

class CloudflareApi {
  readonly baseUrl: string;
  readonly headers: HeadersInit;

  constructor(accountId: string, apiToken: string) {
    if (!/^[a-f0-9]{32}$/.test(accountId)) {
      throw new Error("CLOUDFLARE_ACCOUNT_ID is invalid");
    }
    this.baseUrl = `https://api.cloudflare.com/client/v4/accounts/${accountId}`;
    this.headers = {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    };
  }

  get<T>(path: string): Promise<T> {
    return this.request<T>(path, "GET");
  }

  post<T>(path: string, body: Record<string, unknown>): Promise<T> {
    return this.request<T>(path, "POST", body);
  }

  put<T>(path: string, body: Record<string, unknown>): Promise<T> {
    return this.request<T>(path, "PUT", body);
  }

  private async request<T>(
    path: string,
    method: "GET" | "POST" | "PUT",
    body?: Record<string, unknown>,
  ): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: this.headers,
      body: body ? JSON.stringify(body) : undefined,
      redirect: "error",
    });
    const envelope = (await response.json()) as CloudflareEnvelope<T>;
    if (!response.ok || !envelope.success) {
      const detail =
        envelope.errors?.map((error) => error.message).filter(Boolean).join("; ") ||
        `HTTP ${response.status}`;
      throw new Error(`Cloudflare API request failed for ${path}: ${detail}`);
    }
    return envelope.result;
  }
}

try {
  const apply = process.argv.includes("--apply");
  const accountId = requiredEnvironment("CLOUDFLARE_ACCOUNT_ID");
  const apiToken = requiredEnvironment("CLOUDFLARE_ACCESS_API_TOKEN");
  const result = await separateAccessGroups(
    new CloudflareApi(accountId, apiToken),
    apply,
  );
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : "Access group separation failed");
  process.exitCode = 1;
}

export {};
