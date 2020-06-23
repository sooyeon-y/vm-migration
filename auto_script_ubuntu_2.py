from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver
import subprocess
import time
import re

# user input side

vpc_name = 'testvpc'
selected_region = 'us-east1'

source_machine_list = ['192.168.56.103', '192.168.56.101']

default_path = '/home/user'

# initial setting: ansible fetch
subprocess.call('ansible-playbook playbook_1017.yml --extra-vars "ansible_sudo_pass=####"', shell=True)

# only first loop -> network setting
loop_count = 1

# migration user app & data list
user_app_dir_list = [['/var/www/html','/home/ubuntu'],['/var/www/html']]

for machine_ip in source_machine_list:

	private_ip = ''
	subnet_list = set()
	firewall_rules = []

	flavor = []
	image_file_name = ''

	app_list = []

	#user_app_dir = '/var/www/html'
	#if loop_count == 2:
	#	user_app_dir = '/home'

# find network informations
	
	with open(machine_ip + default_path + '/netinfo.txt', 'r') as net_file:
		while True:
			txt = net_file.readline()
			#print(txt.find('inet addr:'))
			if txt.find('inet addr:192') != -1:
				temp_arr = txt.split('  ')
				temp_arr2 = temp_arr[5].split(':')
				print(temp_arr, temp_arr2)
				private_ip = temp_arr2[1]
				temp_arr3 = temp_arr[6].split(':')
				subnet_list.add(temp_arr3[1].replace('255', '0'))
			if private_ip != '' and subnet_list != '':
				break

	# find firewall rules			

	# decide image (from OS Name/Version)

	os_version = ''
	os_name = ''

	with open(machine_ip + default_path + '/osinfo.txt', 'r') as os_file:
		while True:
			txt = os_file.readline()
			if txt.startswith('DISTRIB_ID'):
				temp_arr = txt.split('=')
				os_name = temp_arr[-1]
			elif txt.startswith('DISTRIB_RELEASE'):
				temp_arr = txt.split('=')
				os_version = temp_arr[-1]

			if os_name != '' and os_version != '':
				print("osinfo executing")
				break

	if os_name == 'Ubuntu\n' and os_version == '14.04\n':
		image_file_name = 'ubuntu-1404-trusty-v20180818'
	elif os_name == 'Ubuntu\n' and os_version == '16.04\n':
		image_file_name = 'ubuntu-1604-xenial-v20180814'
	elif os_name == 'Ubuntu\n' and os_version == '18.04\n':
		image_file_name = 'ubuntu-1804-bionic-v20180814'
	elif os_name == 'Debian\n':
		image_file_name = 'debian-9-stretch-v20180820'

	# decide flavor

	cpu_num = ''
	cpu_power = ''
	memory_size = ''

	with open(machine_ip + default_path + '/cpuinfo.txt', 'r') as cpu_file:
		while True:
			txt = cpu_file.readline()
			if txt.startswith('cpu MHz'):
				temp_arr = txt.split(':')
				cpu_power = temp_arr[-1]
			elif txt.startswith('cpu cores'):
				temp_arr = txt.split(':')
				cpu_num = temp_arr[-1]
			if cpu_power != '' and cpu_num != '':
				print('cpuinfo executing')
				break

	with open(machine_ip + default_path + '/meminfo.txt', 'r') as mem_file:
		while True:
			txt = mem_file.readline()
			if txt.startswith('MemTotal'):
				temp_arr = txt.split(':')
				memory_size = temp_arr[-1]
			if memory_size != '':
				break

	memory_size = re.findall("\d+", memory_size) # find number in string (using R.E)

	cpu_total_pow = float(cpu_power) * int(cpu_num)
	memory_size = int(memory_size[0]) / 1024

	# unit: MHz / MB
	# google vCPU = 2.5GHz Intel Xeon CPU?
	if cpu_total_pow > 20000 or memory_size > 30000:
		flavor = 'n1-standard-16'
	elif cpu_total_pow > 10000 or memory_size > 15000:
		flavor = 'n1-standard-8'
	elif cpu_total_pow > 5000 or memory_size > 7500:
		flavor = 'n1-standard-4'
	elif cpu_total_pow > 2500 or memory_size > 3750:
		flavor = 'n1-standard-2'
	else:
		flavor = 'n1-standard-1'

	# find installed SWs from apt-get

	with open(machine_ip + default_path + '/applog.txt', 'r') as app_file:
		while True:
			txt = app_file.readline()
			#print(txt.find('inet addr:'))
			if txt.find('apt-get install') != -1:
				temp_arr = txt.split(' ')
				app_list.append(temp_arr[3].strip())
			if len(txt) == 0:
				break

	print(private_ip, subnet_list, flavor, image_file_name)
	print(app_list)

	# API Call Start

	if loop_count == 1:

		email = '######' # Access Key
		pem_path = '######' # Secret Key
		project_name = '######'

		ComputeEngine = get_driver(Provider.GCE)
		driver = ComputeEngine(email, pem_path, project=project_name)

		print(len(subnet_list))

		# Network Setting
		driver.ex_create_network(vpc_name, '', mode='custom')

		while len(subnet_list) > 0:
			subnet_name = 'subnet' + str(len(subnet_list))
			subnet = subnet_list.pop()
			driver.ex_create_subnetwork(subnet_name, cidr=subnet+'/24', network=vpc_name, region=selected_region)

		#driver.ex_create_firewall('allow-ssh2', [{'IPProtocol': 'tcp', 'ports': ['22'],}], network=vpc_name)
		driver.ex_create_firewall('allow-http', [{'IPProtocol': 'tcp', 'ports': ['80'],}], network=vpc_name)
		driver.ex_create_firewall('allow-ssh', [{'IPProtocol': 'tcp', 'ports': ['22'],}], network=vpc_name)

	# Ansible Script Ready (Application Migration)

	# user app
	with open('playbook_app.yml', 'w') as playbook:
		playbook.write('- hosts: ' + machine_ip + '\n')
		playbook.write('  tasks:\n')			# YAML don't use 'tab'
		app_no = 1
		for user_app_dir in user_app_dir_list[loop_count-1]:
			#app_no = 1
			playbook.write('    - name: tar zip\n')
			playbook.write('      become: true\n')	# w/o this line -> error
			playbook.write('      shell: tar -zcvf app' + str(app_no) + '.tar.gz ' + user_app_dir + '\n')
			playbook.write('    - name: fetch\n')
			playbook.write('      become: true\n')	# w/o this line -> error
			playbook.write('      fetch: src=/home/user/app' + str(app_no) + '.tar.gz dest=/home/user\n')
			app_no += 1
	
	subprocess.call('ansible-playbook playbook_app.yml --extra-vars "ansible_sudo_pass=159357"', shell=True)

	# apt-get install app
	with open('playbook.yml', 'w') as playbook:
		playbook.write('- hosts: all\n')
		playbook.write('  tasks:\n')			# YAML don't use 'tab'
		playbook.write('    - name: create user node\n')
		playbook.write('      become: true\n')	# w/o this line -> error
		playbook.write('      user:\n')
		playbook.write('         name: nodejs\n')
		playbook.write('         state: present\n')

		for app in app_list: # app install
			playbook.write('    - name: install ' + app + '\n')
			playbook.write('      become: true\n')
			playbook.write('      shell: sudo apt-get -y install ' + app + '\n')# + '=' + app_version)

	# Packer Script (Machine Construction)

	print('packer start...')

	with open('packer_script.json', 'w') as packer_script:
		packer_script.write('{\n')
		packer_script.write('"variables":{\n')
		packer_script.write('"project_id":"'+ project_name + '",\n')
		packer_script.write('"prefix":"packer"\n')
		packer_script.write('},\n\n')
		packer_script.write('"builders":[\n')
		packer_script.write('{\n')
		packer_script.write('"type":"googlecompute",\n')
		packer_script.write('"account_file":"'+ pem_path + '",\n')
		packer_script.write('"project_id":"{{user `project_id`}}",\n')
		packer_script.write('"source_image":"' + image_file_name + '",\n') # source_image
		packer_script.write('"zone":"us-central1-a",\n')
		packer_script.write('"ssh_username":"nodejs",\n')
		packer_script.write('"image_name":"{{user `prefix`}}-' + str(loop_count) + '",\n')
		packer_script.write('"machine_type":"' + flavor + '"\n') # machine_type
		packer_script.write('}\n')
		packer_script.write('],\n\n')
		
		packer_script.write('"provisioners":[\n')
		packer_script.write('{\n')

		packer_script.write('"type":"shell",\n')
		packer_script.write('"inline":["sudo chown nodejs: /home"]\n')
		packer_script.write('},\n')
		app_no = 1
		for i in user_app_dir_list[loop_count-1]:
			#app_no = 1
			packer_script.write('{\n')
			packer_script.write('"type":"file",\n')
			packer_script.write('"source":"' + machine_ip + default_path +'/app' + str(app_no) + '.tar.gz",\n')
			packer_script.write('"destination":"/home/app' + str(app_no) + '.tar.gz"\n')
			packer_script.write('},\n')

			packer_script.write('{\n')
			packer_script.write('"type":"shell",\n')
			packer_script.write('"inline":["sudo tar -zxvf /home/app' + str(app_no) + '.tar.gz -C /"]\n')
			packer_script.write('},\n')
			app_no += 1

		packer_script.write('{\n')
		packer_script.write('"type":"shell",\n')
		packer_script.write('"execute_command":"echo ''install ansible'' | {{ .Vars }} sudo -E -S sh ''{{ .Path }}''",\n')
		packer_script.write('"inline":[\n')
		packer_script.write('"sleep 30",\n')
		packer_script.write('"apt-add-repository ppa:ansible/ansible",\n') # to fix ubuntu error... this line?
		packer_script.write('"/usr/bin/apt-get update",\n')
		packer_script.write('"/usr/bin/apt-get -y install ansible"\n')
		packer_script.write(']\n')
		packer_script.write('},\n')
		packer_script.write('{\n')
		packer_script.write('"type":"ansible-local",\n')
		packer_script.write('"playbook_file":"playbook.yml"\n')
		packer_script.write('}')

		packer_script.write(']')
		packer_script.write('}')

	subprocess.call('packer build packer_script.json', shell=True)

	#time.sleep(300)

	# Start Instance

	instance_name = 'instance-' + str(loop_count)

	driver.create_node(instance_name,flavor,'packer-'+str(loop_count), location=selected_region+'-b', ex_network=vpc_name, ex_subnetwork=subnet_name, internal_ip=private_ip)

	loop_count += 1
