
start /min cmd /K C:\\Users\\TrappedIonriceXPS\\anaconda3\\Scripts\\activate.bat ^& conda activate artiq_7_test2 ^& ping 192.168.1.70 ^& aqctl_moninj_proxy --port-proxy 1383 --port-control 1384 --bind ::1 192.168.1.70

start /min cmd /K C:\\Users\\TrappedIonriceXPS\\anaconda3\\Scripts\\activate.bat ^& conda activate artiq_7_test2^& artiq_master

start /min cmd /K C:\\Users\\TrappedIonriceXPS\\anaconda3\\Scripts\\activate.bat ^& conda activate artiq_7_test2 ^& artiq_dashboard -p ndscan.dashboard_plugin
