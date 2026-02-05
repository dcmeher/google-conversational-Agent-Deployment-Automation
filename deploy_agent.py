#make sure to run  this command  : gcloud auth application-default login  and update .env 
#if you receive any permission error ,run  this command ( replace PROJECT_ID ):  gcloud auth application-default set-quota-project se-gcp-348466
import os
import sys
import logging
from datetime import datetime, UTC
from google.cloud import dialogflowcx_v3beta1 as dialogflow
from google.protobuf import field_mask_pb2
from dotenv import load_dotenv

# -----------------------------
# UTF-8 safety for Windows
# -----------------------------
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.getenv("LOCATION")
AGENT_ID = os.getenv("AGENT_ID")
ENV_DISPLAY_NAME = os.getenv("ENV_DISPLAY_NAME")
BUILD_DISPLAY_NAME = os.getenv("BUILD_DISPLAY_NAME")

if LOCATION == "global":
    CX_CLIENT_OPTIONS = None
else:
    CX_CLIENT_OPTIONS = {
        "api_endpoint": f"{LOCATION}-dialogflow.googleapis.com"
    }

# -----------------------------
# Logging setup
# -----------------------------
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

log_file = os.path.join(
    LOG_DIR,
    f"df_deploy_agent-{AGENT_ID}_env-{ENV_DISPLAY_NAME}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.log"
)

file_handler = logging.FileHandler(log_file, encoding="utf-8")
console_handler = logging.StreamHandler(sys.stdout)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[file_handler, console_handler]
)

logger = logging.getLogger(__name__)
# -------------------------------------------------
# Validation (FAIL FAST)
# -------------------------------------------------
def validate_config():
    required = {
        "PROJECT_ID": PROJECT_ID,
        "LOCATION": LOCATION,
        "AGENT_ID": AGENT_ID,
        "ENV_DISPLAY_NAME": ENV_DISPLAY_NAME,
        "BUILD_DISPLAY_NAME": BUILD_DISPLAY_NAME,
    }

    missing = [k for k, v in required.items() if not v]
    if missing:
        print("\n Missing required environment configuration:\n")
        for name in missing:
            print(f"  - {name}")
        print("\nPlease set the missing environment variable(s) and try again.\n")
        sys.exit(1)

def confirm_deployment(agent_display_name):
    print("\n================ DEPLOYMENT CONFIRMATION ================")
    print(f"Agent Name       : {agent_display_name}")
    print(f"Agent ID         : {AGENT_ID}")
    print(f"Project          : {PROJECT_ID}")
    print(f"Location         : {LOCATION}")
    print(f"Target Env       : {ENV_DISPLAY_NAME}")
    print(f"Build / Release  : {BUILD_DISPLAY_NAME}")
    print("=========================================================\n")

    response = input("Proceed with deployment? (y/N): ").strip().lower()
    if response not in ("y", "yes"):
        logger.info("Deployment aborted by user.")
        sys.exit(0)

def automate_full_deployment():
    validate_config()
        # -----------------------------
    # Fetch Agent Details
    # -----------------------------
    agent_path = f"projects/{PROJECT_ID}/locations/{LOCATION}/agents/{AGENT_ID}"
    a_client = dialogflow.AgentsClient(client_options=CX_CLIENT_OPTIONS)
    agent = a_client.get_agent(name=agent_path)

    confirm_deployment(agent.display_name)
    # -----------------------------
    # Clients
    # -----------------------------
    v_client = dialogflow.VersionsClient(client_options=CX_CLIENT_OPTIONS)
    f_client = dialogflow.FlowsClient(client_options=CX_CLIENT_OPTIONS)
    p_client = dialogflow.PlaybooksClient(client_options=CX_CLIENT_OPTIONS)
    t_client = dialogflow.ToolsClient(client_options=CX_CLIENT_OPTIONS)
    e_client = dialogflow.EnvironmentsClient(client_options=CX_CLIENT_OPTIONS)

    agent_path = f"projects/{PROJECT_ID}/locations/{LOCATION}/agents/{AGENT_ID}"
    deployable_versions = []

    logger.info(f"--- Starting Deployment for Agent {AGENT_ID} ---")

    # -----------------------------
    # 1. Version Flows (PARALLEL)
    # -----------------------------
    flow_version_ops = []

    for flow in f_client.list_flows(parent=agent_path):
        logger.info(f"[FLOW] Versioning started: {flow.display_name}")

        op = v_client.create_version(
            parent=flow.name,
            version=dialogflow.Version(display_name=BUILD_DISPLAY_NAME)
        )

        flow_version_ops.append((flow.display_name, op))

    # Wait for all flow versions to complete
    for flow_name, op in flow_version_ops:
        version = op.result()
        deployable_versions.append(version.name)
        logger.info(f"→ Created Flow Version: {flow_name}")

    # -----------------------------
    # 2. Version Playbooks (Sync)
    # -----------------------------
    for playbook in p_client.list_playbooks(parent=agent_path):
        logger.info(f"[PLAYBOOK] Versioning: {playbook.display_name}")

        version = p_client.create_playbook_version(
            parent=playbook.name,
            playbook_version=dialogflow.PlaybookVersion(
                description=BUILD_DISPLAY_NAME
            )
        )

        deployable_versions.append(version.name)
        logger.info(f"→ Created Playbook Version: {playbook.display_name}")

    # -----------------------------
    # 3. Version Custom Tools
    # -----------------------------
    for tool in t_client.list_tools(parent=agent_path):
        if "code-interpreter" in tool.display_name.lower():
            continue

        logger.info(f"[TOOL] Versioning & publishing: {tool.display_name}")

        tool_version = t_client.create_tool_version(
            parent=tool.name,
            tool_version=dialogflow.ToolVersion(
                display_name=BUILD_DISPLAY_NAME
            )
        )

        deployable_versions.append(tool_version.name)

    # -----------------------------
    # 4. Create / Update Environment
    # -----------------------------
    envs = list(e_client.list_environments(parent=agent_path))
    target_env = next(
        (e for e in envs if e.display_name.lower() == ENV_DISPLAY_NAME.lower()),
        None
    )

    version_configs = [
        dialogflow.Environment.VersionConfig(version=v)
        for v in deployable_versions
    ]

    if not target_env:
        logger.info(f"[ENV] Creating environment '{ENV_DISPLAY_NAME}'")

        op = e_client.create_environment(
            parent=agent_path,
            environment=dialogflow.Environment(
                display_name=ENV_DISPLAY_NAME,
                version_configs=version_configs
            )
        )

        target_env = op.result()
        logger.info(f"[ENV] Created environment: {target_env.name}")

    else:
        logger.info(f"[ENV] Updating environment '{ENV_DISPLAY_NAME}'")

        update_mask = field_mask_pb2.FieldMask(paths=["version_configs"])
        env_update = dialogflow.Environment(
            name=target_env.name,
            version_configs=version_configs
        )

        op = e_client.update_environment(
            environment=env_update,
            update_mask=update_mask
        )
        op.result()

    logger.info("--- Deployment Complete ---")
    logger.info(f"Total versions deployed: {len(deployable_versions)}")
    logger.info("Tools: versioned globally (latest always active)")


if __name__ == "__main__":
    try:
        automate_full_deployment()
    except Exception:
        logger.exception("❌ Deployment failed")
        raise
