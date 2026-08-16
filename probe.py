import os
import sys
import time
import json
import random
import datetime
import subprocess
import urllib.request
import urllib.parse

USER_OCID = os.environ.get("OCI_USER_OCID", "")
TENANCY_OCID = os.environ.get("OCI_TENANCY_OCID", "")
FINGERPRINT = os.environ.get("OCI_FINGERPRINT", "")
REGION = os.environ.get("OCI_REGION", "ap-hyderabad-1")
KEY_CONTENT = os.environ.get("OCI_KEY_CONTENT", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

AD_NAME = "PMjr:AP-HYDERABAD-1-AD-1"
SUBNET_ID = "ocid1.subnet.oc1.ap-hyderabad-1.aaaaaaaaq2tq54kwpfc4zuyl7pzclmgbzluyzb6eecmaa4dgug7ww5agbocq"
IMAGE_ID = "ocid1.image.oc1.ap-hyderabad-1.aaaaaaaaxa7c32msqiu4ueamqtpl6oz4gqfs7vd5tbro64nyyi6qkoor4w6a"
SSH_PUB_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMenDM+UTe3lplGdtrlbF6aTmEgH5DsQHgolPJK6EQ+o kevin@nixos"

def setup_oci_config():
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

    # Write SSH key for VM
    with open("/tmp/id_rsa.pub", "w") as f:
        f.write(SSH_PUB_KEY.strip() + "\n")

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown"
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

    # Perform up to 3 launch attempts per workflow execution
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        print(f"[{datetime.datetime.now()}] Attempt {attempt}/{max_attempts}: Sending launch request to ap-hyderabad-1...")
        success, output = try_launch()

        if success:
            print("SUCCESS! Arm VM was provisioned!")
            try:
                data = json.loads(output).get("data", {})
                inst_id = data.get("id")
                display_name = data.get("display-name", "openwebui-arm")
            except:
                inst_id = "Created"
                display_name = "openwebui-arm"

            time.sleep(30)
            public_ip = "Available in OCI Console"
            try:
                ip_cmd = f"oci compute instance list-vnics --instance-id {inst_id}"
                ip_res = subprocess.run(ip_cmd, shell=True, capture_output=True, text=True)
                vnic_data = json.loads(ip_res.stdout).get("data", [])
                if vnic_data:
                    public_ip = vnic_data[0].get("public-ip", public_ip)
            except:
                pass

            msg = (
                f"🎉🎉 *VICTORY! ARM INSTANCE PROVISIONED VIA GITHUB ACTIONS!* 🎉🎉\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💻 *Instance*: `{display_name}`\n"
                f"🌐 *Public IP*: `{public_ip}`\n"
                f"⚙️ *Specs*: 2 OCPUs | 12 GB RAM | 100 GB NVMe Storage\n"
                f"💰 *Cost*: **Always Free ($0.00 / month forever)**\n\n"
                f"🚀 *Connect from your NixOS terminal*:\n"
                f"`ssh ubuntu@{public_ip}`\n\n"
                f"GitHub Actions capacity hunt is complete!"
            )
            send_telegram(msg)
            sys.exit(0)
        else:
            if "Out of host capacity" in output:
                print("Result: Out of host capacity in Hyderabad AD-1.")
            elif "TooManyRequests" in output:
                print("Result: Rate limit reached, backing off.")
            else:
                print(f"Result: {output.strip().splitlines()[-1][:100]}")

            if attempt < max_attempts:
                sleep_sec = 85 + random.randint(5, 20)
                print(f"Sleeping {sleep_sec}s before next attempt...")
                time.sleep(sleep_sec)

    print(f"[{datetime.datetime.now()}] Batch finished. Clean exit until next scheduled run.")

if __name__ == "__main__":
    main()
