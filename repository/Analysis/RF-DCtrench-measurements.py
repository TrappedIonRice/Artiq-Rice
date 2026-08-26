import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
# Define your data points
# importing files

filedirectory=""
filename=""
WS = pd.read_excel(filename+'.xlsx')
WS_np = np.array(WS)


x = np.array([18.5,18,19,19.5,20,20.5

])
y = np.array([17,22,13.6,12.8, 13.6,  16.8
])

# Perform a quadratic fit (2nd-degree polynomial)
coefficients = np.polyfit(x, y, 2)

# Get the fitted polynomial function
polynomial = np.poly1d(coefficients)

# Generate x values for plotting the fitted curve
x_fit = np.linspace(min(x), max(x), 100)
y_fit = polynomial(x_fit)

# Plot the original data points and the quadratic fit
plt.scatter(x, y, color='red', label='Data Points')
plt.plot(x_fit, y_fit, label='Quadratic Fit', color='blue')


# Add labels and legend
plt.xlabel('x')
plt.ylabel('y')
plt.title('Quadratic Fit')
plt.legend()

# Display the plot
plt.show()

# Print the coefficients of the quadratic fit
print("Quadratic fit coefficients: a = {}, b = {}, c = {}".format(coefficients[0], coefficients[1], coefficients[2]))






