import pyvisa as visa
#rm = visa.ResourceManager()
rm = visa.ResourceManager(r'C:\Windows\System32\visa64.dll')
print(rm.list_resources())