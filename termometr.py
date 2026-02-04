import sys
import os
import time
import subprocess
import glob
import requests
import smbus

# === KONFIGURACJA ===
github_url = "https://raw.githubusercontent.com/dominikolszakolszewski/termometr-iot/refs/heads/main/termometr.py"
current_version = "1.0" 

DATA = {
    'Wolfhagen': {
        'b8:27:aa:aa:aa:aa': {'tid': 'Thermometer_ATW_1', 'correction': 0},
        'b8:27:bb:bb:bb:bb': {'tid': 'Thermometer_ATW_2', 'correction': 0},
    },
    'Ostrow Mazowiecka': {
        'b8:27:cc:cc:cc:cc': {'tid': 'Thermometer_SP_1', 'correction': 0},
    },
    'Biala Podlaska': {
        'b8:27:eb:13:27:63': {'tid': 'Thermometer_ATP_6', 'correction': 1.5},
    },
}

def wait_for_online(host):
    command = ['ping', '-c', '1', host]
    while True:
        try:
            if subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                return True
        except:
            pass
        time.sleep(1)

def self_update():
    try:
        r = requests.get(github_url, timeout=10)
        if r.status_code == 200:
            new_code = r.text
            remote_version = None
            for line in new_code.split('\n'):
                if 'current_version =' in line:
                    try:
                        remote_version = line.split('"')[1]
                    except:
                        continue
                    break
            
            if remote_version and remote_version != current_version:
                with open(__file__, "w", encoding="utf-8") as f:
                    f.write(new_code)
                os.execv(sys.executable, ['python3'] + sys.argv)
    except:
        pass

def get_current_config():
    for iface in ("wlan0", "eth0", "usb0"):
        try:
            path = f"/sys/class/net/{iface}/address"
            if os.path.exists(path):
                with open(path) as f:
                    mac = f.read().strip().lower()
                for loc, devices in DATA.items():
                    if mac in devices:
                        config = devices[mac]
                        config['tid'] = config.get('tid')
                        return config
        except:
            continue
    return None

def read_mcp9808():
    try:
        bus = smbus.SMBus(1)
        data = bus.read_i2c_block_data(0x18, 0x05, 2)
        upper = data[0] & 0x1F
        temp = (upper * 16.0) + (data[1] / 16.0)
        if upper & 0x10:
            temp -= 256.0
        return temp
    except:
        return None

def read_ds18b20():
    try:
        devices = glob.glob('/sys/bus/w1/devices/28*')
        if not devices: return None
        with open(devices[0] + '/w1_slave', 'r') as f:
            lines = f.readlines()
        pos = lines[1].find('t=')
        return float(lines[1][pos+2:]) / 1000.0 if pos != -1 else None
    except:
        return None

def get_measurement(correction):
    temp = read_mcp9808()
    if temp is None: temp = read_ds18b20()
    return round(temp - correction, 1) if temp is not None else None

def send_to_server(tid, temp):
    url = 'http://172.20.10.14:8081/Thermo/Thermo?id={TID}&temperature={TEM}'.format(TID = tid, TEM = round(temp, 1))
    try:
        r = requests.get(url, timeout=5)
        return r.status_code == 200
    except:
        return False

def main():
    wait_for_online("8.8.8.8")
    self_update()
    
    config = get_current_config()
    if not config:
        sys.exit(1)

    tid = config.get('tid')
    correction = config.get('correction', 0)

    while True:
        try:
            temp_val = get_measurement(correction)
            if temp_val is not None:
                send_to_server(tid, temp_val)
            
            time.sleep(1)
        except KeyboardInterrupt:
            break
        except:
            time.sleep(5)

if __name__ == "__main__":
    main()


