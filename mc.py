import numpy as np

# Номинальные значения
R1_nom = 2000  # Пример номинального значения R1
R2_nom = 2000  # Пример номинального значения R2
K_nom = 2.495    # Пример номинального значения K
I_nom = 3e-6   # Пример номинального значения I

# Относительная погрешность 1%
relative_error = 0.01
res_relative_error = 0.01

# Количество итераций Монте-Карло
num_samples = 1000000

# Генерация случайных значений с учетом погрешности
R1_values = np.random.normal(R1_nom, R1_nom * res_relative_error, num_samples)
R2_values = np.random.normal(R2_nom, R2_nom * res_relative_error, num_samples)
K_values = np.random.normal(K_nom, K_nom * relative_error, num_samples)
I_values = np.random.normal(I_nom, I_nom * relative_error, num_samples)

# Вычисление Uвых для каждого набора значений
U_out_values = K_values * (1 + (R1_values / R2_values)) + I_values * R1_values

# Среднее значение Uвых
U_out_mean = np.mean(U_out_values)

# Абсолютная погрешность (стандартное отклонение)
U_out_std = np.std(U_out_values)

# Относительная погрешность
U_out_relative_error = U_out_std / U_out_mean

# Вывод результатов
print(f"Среднее значение Uвых: {U_out_mean:.4f}")
print(f"Абсолютная погрешность Uвых: {U_out_std:.4f}")
print(f"Относительная погрешность Uвых: {U_out_relative_error * 100:.4f}%")