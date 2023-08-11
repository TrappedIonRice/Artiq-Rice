# import matplotlib.pyplot as plt
# from matplotlib.animation import FuncAnimation
# from random import randrange
#
# fig = plt.figure(figsize=(6, 3))
# x = [0]
# y = [0]
#
# ln, = plt.plot(x, y, '-')
# cnt = 0
# while cnt<10:
#     def update(frame):
#         x.append(x[-1] + 1)
#         y.append(randrange(0, 10))
#
#         ln.set_data(x, y)
#         fig.gca().relim()
#         fig.gca().autoscale_view()
#         return ln,
#
#     animation = FuncAnimation(fig, update, interval = 500)
#     plt.show()
#     cnt +=1

# importing libraries
import numpy as np
import time
import matplotlib.pyplot as plt

# # creating initial data values
# # of x and y
# x = np.linspace(0, 10, 100)
# y = np.sin(x)
#
# # to run GUI event loop
# plt.ion()
#
# # here we are creating sub plots
# figure, ax = plt.subplots(figsize=(10, 8))
# line1, = ax.plot(x, y)
#
# # setting title
# plt.title("Geeks For Geeks", fontsize=20)
#
# # setting x-axis label and y-axis label
# plt.xlabel("X-axis")
# plt.ylabel("Y-axis")
#
# # Loop
# for _ in range(50):
#     # creating new Y values
#     new_y = np.sin(x - 0.5 * _)
#
#     # updating data values
#     line1.set_xdata(x)
#     line1.set_ydata(new_y)
#
#     # drawing updated values
#     figure.canvas.draw()
#
#     # This will run the GUI event
#     # loop until all UI events
#     # currently waiting have been processed
#     figure.canvas.flush_events()
#
#     time.sleep(0.1)