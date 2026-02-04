import sys
import os
import time
import subprocess
import platform
import glob
import requests
import smbus
import ntplib

github_url = ""
current_version = 1.0

# KONFIGURACJA URZADZEN

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
	try:
		response = requests.get(github_url, timeout = 10)
		if response.status_code == 200:
			new_code = response.txt
				
			for line in new_code.split('\n'):
				if 'current version =' in line:
					try:
						remote_version = line.split('"')[1]
					except IndexError:
						continue
					break
					
			if remote_version != current_version:
				with open(__file__, "w", encoding="utf-8") as f:
					f.write(new_code)
				os.execv(sys.executable, ['python3'] + sys.argv)
	except:
		pass
		
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
						return config
						print(f"Znaleziono konfiguracje dla {mac} {loc}")
		except Exception as e:
			print(f"Blad podczas sprawdzania interfejsu {iface}: {e}")
			continue
	print("Nie znaleziono urzadzenia w bazie")
	return None

# OBSLUGA CZASU
def get_gum_time_string():
	client = ntplib.NTPClient()
	server = 'tempus1.gum.gov.pl'
	
	wait_for_online(server)
	
	while True:
		try:
			response = client.request(server, version=3, timeout=2)
			return time.strftime('%Y:%m:%d:%H:%M:%S', time.localtime(response.tx_time))
		except Exception as e:
			print(f"Blad pobierania czasu NTP")
			time.sleep(1)

# POMIAR TEMPERATURY
def read_mcp9808():
	try:
		bus = smbus.SMBus(1)
		data = bus.read_i2c_block_data(0x18, 0x05, 2)
		u, l = data[0] & 0x1F, data[1] / 16.0
		return (u * 16 + l) - 256 if data[0] & 0x10 else u * 16 + l
	except Exception:
		return None
		
def read_ds18b20():
	try:
		devices = glob.glob('/sys/bus/w1/devices/28*')
		if not devices:
			return None
		
		folder = devices[0]
		with open(folder + '/w1_slave', 'r') as f:
			lines = f.readlines()
			
		if len(lines) < 2:
			return None
		
		pos = lines[1].find('t=')
		return float(lines[1][pos+2:]) / 1000.0 if pos != -1 else None
	except Exception:
		return None
		
def get_measurement(correction):
	temp = read_mcp9808()
	
	if temp is None:
		temp = read_ds18b20()
	
	if temp is not None:
		final_temp = temp + correction
		return round(final_temp, 1)
	else:
		return None

# WYSYLANIE DANYCH
def send_to_server(tid, temp):
	if temp is None:
		return False
	
	#url = 'http://data-grabber.int.aluteam.pl:8081/Thermo/Thermo?id={TID}&temperature={TEM}'.format(TID = tid, TEM = round(temp, 1))
	url = 'http://192.168.1.106:8081/Thermo/Thermo?id={TID}&temperature={TEM}'.format(TID = tid, TEM = round(temp, 1))
	
	try:
		response = requests.get(url, timeout = 5)
		if response.status_code == 200:
			return True
	except Exception as e:
		print(f"Blad wysylania: {e}")
		
	return False
	
# WLASCIWY PROGRAM
def main():
	config = get_current_config()
	
	if not config:
		print('KRYTYCZNY BLAD: NIE ROZPOZNANO URZADZENIA')
		return 
	
	tid = config.get('tid')
	correction = config.get('correction', 0)
	
	print(f"Start systemu. TID: {tid}, Korekta: {correction}")
	
	while True:
		try:
			wait_for_online("8.8.8.8")
			
			timestamp_gum = get_gum_time_string()
			temp_val = get_measurement(correction)
			
			if temp_val is not None:
				log_msg = f"Czas: {timestamp_gum} | Temp: {temp_val}"
				print(log_msg)
				
				if send_to_server(tid, temp_val):
					print("WYSLANE")
				else:
					print("BLAD WYSYLANIA")
			else:
				print(f"[{timestamp_gum}] Blad odczytu temperatury")
				
			time.sleep(1)
		
		except KeyboardInterrupt:
			break 
		except Exception as e:
			print(f" Wystapil blad: {e}")
			time.sleep(5)
			
if __name__ == "__main__":
	main()