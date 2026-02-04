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
        'b8:27:eb:13:27:63': {'tid': 'Thermometer_ATP_6', 'correction': -1.5},
    },
}

# FUNKCJE SIECIOWE
def wait_for_online(host):
    command = ['ping', '-c', '1', host]
    while True:
        try:
            if subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                return True
        except Exception:
            pass
        time.sleep(1)

# KONTROLA WERSJI 
def self_update():
    print(f"Sprawdzanie aktualizacji... (Wersja: {current_version})")
    try:
        r = requests.get(github_url, timeout=10)
        if r.status_code == 200:
            new_code = r.text
            remote_version = None
            for line in new_code.split('\n'):
                if 'current_version =' in line:
                    try:
                        remote_version = line.split('"')[1]
                    except IndexError:
                        continue
                    break
            
            if remote_version and remote_version != current_version:
                print(f"Aktualizacja do wersji: {remote_version}...")
                with open(__file__, "w", encoding="utf-8") as f:
                    f.write(new_code)
                os.execv(sys.executable, ['python3'] + sys.argv)
            else:
                print("Wersja aktualna.")
    except Exception as e:
        print(f"Blad aktualizacji: {e}")

# IDENTYFIKACJA MAC
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
                        config['location'] = loc
                        config['mac'] = mac
                        print(f"Zidentyfikowano: {mac} ({loc})")
                        return config
        except:
            continue
    return None

# POMIAR TEMPERATURY
def read_mcp9808():
    try:
        bus = smbus.SMBus(1)
        data = bus.read_i2c_block_data(0x18, 0x05, 2)
        u, l = data[0] & 0x1F, data[1] / 16.0
        return (u * 16 + l) - 256 if data[0] & 0x10 else u * 16 + l
    except: return None

def read_ds18b20():
    try:
        devices = glob.glob('/sys/bus/w1/devices/28*')
        if not devices: return None
        folder = devices[0]
        with open(folder + '/w1_slave', 'r') as f:
            lines = f.readlines()
        pos = lines[1].find('t=')
        return float(lines[1][pos+2:]) / 1000.0 if pos != -1 else None
    except: return None

def get_measurement(correction):
    temp = read_mcp9808()
    if temp is None: temp = read_ds18b20()
    if temp is not None:
        return round(temp + correction, 1)
    return None

# WYSYLANIE DANYCH
def send_to_server(tid, temp):
    #url = 'http://data-grabber.int.aluteam.pl:8081/Thermo/Thermo?id={TID}&temperature={TEM}'.format(TID = tid, TEM = round(temp, 1))
    url = f'http://172.20.10.14:8081/Thermo/Thermo?id={TEM}&temperature={TEM}'.format(TID = tid, TEM = round(temp, 1)
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except:
        return False

# WLASCIWY PROGRAM
def main():
    wait_for_online("8.8.8.8")
    self_update()
    
    config = get_current_config()
    if not config:
        print('KRYTYCZNY BLAD: NIE ROZPOZNANO URZADZENIA')
        return 

    tid = config.get('tid')
    correction = config.get('correction', 0)
    print(f"Start systemu. TID: {tid}, Korekta: {correction}")

    while True:
        try:
            # Uzywamy czasu systemowego Raspberry Pi
            now = time.strftime('%Y-%m-%d %H:%M:%S')
            temp_val = get_measurement(correction)
            
            if temp_val is not None:
                print(f"[{now}] Temp: {temp_val} C")
                if send_to_server(tid, temp_val):
                    print("WYSLANE")
                else:
                    print("BLAD WYSYLANIA")
            else:
                print(f"[{now}] Blad odczytu czujnika")
                
            time.sleep(1)
        except KeyboardInterrupt:
            break 
        except Exception as e:
            print(f"Blad: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()

