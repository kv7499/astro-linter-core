import os
import sys
import time
import json
import random
import datetime
import subprocess
import urllib.request
import urllib.parse
import html

# Environment Variables from Encrypted Secrets
USER_OCID = os.environ.get("OCI_USER_OCID", "")
TENANCY_OCID = os.environ.get("OCI_TENANCY_OCID", "")
FINGERPRINT = os.environ.get("OCI_FINGERPRINT", "")
REGION = os.environ.get("OCI_REGION", "ap-hyderabad-1")
KEY_CONTENT = os.environ.get("OCI_KEY_CONTENT", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

AD_NAME = os.environ.get("OCI_AD_NAME", "")
SUBNET_ID = os.environ.get("OCI_SUBNET_ID", "")
IMAGE_ID = os.environ.get("OCI_IMAGE_ID", "")
SSH_PUB_KEY = os.environ.get("OCI_SSH_PUB_KEY", "")

def setup_oci_config():
    try:
        oci_dir = os.path.expanduser("~/.oci")
        os.makedirs(oci_dir, exist_ok=True)
        key_path = os.path.join(oci_dir, "oci_api_key.pem")
        with open(key_path, "w") as f:
            f.write(KEY_CONTENT.strip() + "\n")
        os.chmod(key_path, 0o600)

        config_path = os.path.join(oci_dir, "config")
        config_content = f"""[DEFAULT]
user={USER_OCID}
fingerprint={FINGERPRINT}
key_file={key_path}
tenancy={TENANCY_OCID}
region={REGION}
"""
        with open(config_path, "w") as f:
            f.write(config_content)
        os.chmod(config_path, 0o600)

        # Write SSH public key for target VM
        with open("/tmp/id_rsa.pub", "w") as f:
            f.write(SSH_PUB_KEY.strip() + "\n")
    except Exception as e:
        print(f"Error setting up OCI config: {e}")
        sys.exit(1)

def send_telegram(html_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": html_text,
            "parse_mode": "HTML"
        }).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            pass
    except Exception as e:
        print(f"Telegram notification error: {e}")

def try_launch():
    cmd = [
        "oci", "compute", "instance", "launch",
        "--compartment-id", TENANCY_OCID,
        "--availability-domain", AD_NAME,
        "--shape", "VM.Standard.A1.Flex",
        "--shape-config", json.dumps({"ocpus": 2, "memoryInGBs": 12}),
        "--image-id", IMAGE_ID,
        "--subnet-id", SUBNET_ID,
        "--display-name", "openwebui-arm",
        "--assign-public-ip", "true",
        "--boot-volume-size-in-gbs", "100",
        "--ssh-authorized-keys-file", "/tmp/id_rsa.pub"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        return True, res.stdout
    return False, res.stderr

def main():
    print(f"[{datetime.datetime.now()}] Initializing OCI Capacity Probe on GitHub Actions...")
    setup_oci_config()

    # Perform 6 continuous launch attempts per workflow execution (~9.5 minutes of continuous polling)
    max_attempts = 6
    for attempt in range(1, max_attempts + 1):
        print(f"[{datetime.datetime.now()}] Attempt {attempt}/{max_attempts}: Sending launch request to {REGION}...")
        success, output = try_launch()

        if success:
            print("SUCCESS! Arm VM was provisioned!")
            try:
                data = json.loads(output).get("data", {})
                inst_id = data.get("id", "")
                display_name = data.get("display-name", "openwebui-arm")
            except Exception as e:
                inst_id = ""
                display_name = "openwebui-arm"

            time.sleep(30)
            public_ip = "Available in OCI Console"
            if inst_id:
                try:
                    ip_cmd = ["oci", "compute", "instance", "list-vnics", "--instance-id", inst_id]
                    ip_res = subprocess.run(ip_cmd, capture_output=True, text=True)
                    vnic_data = json.loads(ip_res.stdout).get("data", [])
                    if vnic_data:
                        public_ip = vnic_data[0].get("public-ip", public_ip)
                except Exception as e:
                    print(f"Error fetching public IP: {e}")

            msg = (
                f"🎉🎉 <b>VICTORY! ARM INSTANCE PROVISIONED!</b> 🎉🎉\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💻 <b>Instance</b>: <code>{html.escape(display_name)}</code>\n"
                f"🌐 <b>Public IP</b>: <code>{html.escape(public_ip)}</code>\n"
                f"⚙️ <b>Specs</b>: 2 OCPUs | 12 GB RAM | 100 GB NVMe Storage\n"
                f"💰 <b>Cost</b>: <b>Always Free ($0.00 / month forever)</b>\n\n"
                f"🚀 <b>Connect from your terminal</b>:\n"
                f"<code>ssh ubuntu@{html.escape(public_ip)}</code>\n\n"
                f"GitHub Actions capacity hunt is complete!"
            )
            send_telegram(msg)
            sys.exit(0)
        else:
            if "Out of host capacity" in output:
                print(f"Result: Out of host capacity in {AD_NAME}.")
            elif "TooManyRequests" in output:
                print("Result: Rate limit reached (HTTP 429). Exiting current batch cleanly to allow backoff...")
                sys.exit(0)
            else:
                last_line = output.strip().splitlines()[-1] if output.strip().splitlines() else "Unknown error"
                print(f"Result: {last_line[:100]}")

            if attempt < max_attempts:
                sleep_sec = 85 + random.randint(5, 20)
                print(f"Sleeping {sleep_sec}s before next attempt...")
                time.sleep(sleep_sec)

    print(f"[{datetime.datetime.now()}] Batch finished. Clean exit until next scheduled run.")

if __name__ == "__main__":
    main()
