
start /min cmd /K C:\\Users\\TrappedIonRice4\\anaconda3\\Scripts\\activate.bat ^& conda activate artiq_8 ^& ping 192.168.1.20 ^& aqctl_moninj_proxy --port-proxy 1383 --port-control 1384 --bind ::1 192.168.1.20

start /min cmd /K C:\\Users\\TrappedIonRice4\\anaconda3\\Scripts\\activate.bat ^& conda activate artiq_8 ^& artiq_master

start /min cmd /K C:\\Users\\TrappedIonRice4\\anaconda3\\Scripts\\activate.bat ^& conda activate artiq_8 ^& artiq_dashboard -p ndscan.dashboard_plugin || pause
