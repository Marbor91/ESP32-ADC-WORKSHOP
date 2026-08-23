import serial
import serial.tools.list_ports
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import re
from time import sleep, time
import ctypes
import sys
import os
import numpy as np

class SerialPlotter:
    def __init__(self, master):
        self.master = master
        master.title("График данных с COM-порта")

        if os.name == 'nt' and not ctypes.windll.shell32.IsUserAnAdmin():
            messagebox.showerror("Ошибка", "Запустите программу от имени администратора!")
            sys.exit(1)

        # Оптимизация
        plt.rcParams['path.simplify'] = True
        plt.rcParams['path.simplify_threshold'] = 1.0
        plt.rcParams['lines.antialiased'] = False
        plt.rcParams['backend'] = 'TkAgg'
        plt.rcParams['figure.dpi'] = 80

        # Параметры
        self.samples_per_batch = 500
        self.max_points_vertical = 4000
        self.sample_rate = 1000
        self.post_pause = 1000

        # Состояния
        self.is_connected = False
        self.is_accepting = False
        self.serial_port = None
        self.ser = None
        self.data = {}
        self.line_names = []
        self.buffer = ""
        self.serial_thread = None
        self.show_raw_data = False
        self.data_counter = 0
        self._update_id = None
        self.user_zoom = False

        # Панорамирование
        self.is_panning = False
        self.pan_start_x = 0
        self.pan_start_ydata = 0
        self.pan_start_xlim = (0, 1)
        self.pan_start_ylim = (0, 1)

        # Параметры отображения
        self.plot_mode = tk.StringVar(value="Линии+точки")
        self.line_width = tk.DoubleVar(value=1.0)
        self.auto_mode = tk.BooleanVar(value=False)

        self.lines = {}

        self.create_widgets()

        self.figure, self.ax = plt.subplots(figsize=(8, 4), dpi=80)
        self.figure.set_facecolor('#f0f0f0')
        self.ax.set_facecolor('#f0f0f0')
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.frame_right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.ax.grid(True)
        self.clear_graph()

        self.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.canvas.mpl_connect('button_press_event', self.on_press)
        self.canvas.mpl_connect('button_release_event', self.on_release)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)

        self.update_settings()

    def create_widgets(self):
        self.master.grid_columnconfigure(0, weight=0, minsize=250)
        self.master.grid_columnconfigure(1, weight=1)
        self.master.grid_rowconfigure(0, weight=1)

        self.frame_left = ttk.Frame(self.master, padding="5")
        self.frame_left.grid(row=0, column=0, sticky=tk.N+tk.S+tk.W+tk.E)
        self.frame_right = ttk.Frame(self.master)
        self.frame_right.grid(row=0, column=1, sticky=tk.N+tk.S+tk.E+tk.W)

        style = ttk.Style()
        style.configure('TButton', padding=5)
        style.configure('TCheckbutton', padding=5)

        # ---- Группа 1: Порт и связь ----
        group1 = ttk.LabelFrame(self.frame_left, text="Порт и связь", padding="5")
        group1.pack(fill=tk.X, pady=2)

        row = 0
        ttk.Label(group1, text="COM-порт:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.port_list = ttk.Combobox(group1, state="readonly")
        self.port_list.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.port_list.bind("<Button-1>", self.update_port_list)
        self.update_port_list()
        self.connect_btn = ttk.Button(group1, text="Connect", command=self.toggle_connect)
        self.connect_btn.grid(row=row, column=2, padx=5, pady=5)
        row += 1

        ttk.Label(group1, text="Скорость (бод):").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.baud_list = ttk.Combobox(group1,
                                    values=[9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600, 2000000, 4000000],
                                    state="readonly")
        self.baud_list.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.baud_list.set(921600)
        row += 1

        ttk.Label(group1, text="Отправить:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.send_entry = ttk.Entry(group1)
        self.send_entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.send_entry.bind("<Return>", lambda event: self.send_data())
        self.send_btn = ttk.Button(group1, text="Отправить", command=self.send_data)
        self.send_btn.grid(row=row, column=2, padx=5, pady=5)
        row += 1

        self.raw_data_var = tk.BooleanVar()
        self.raw_data_cb = ttk.Checkbutton(group1, text="Показывать сырые данные",
                                          variable=self.raw_data_var,
                                          command=self.toggle_raw_data)
        self.raw_data_cb.grid(row=row, column=0, columnspan=3, padx=5, pady=5, sticky=tk.W)
        row += 1
        group1.grid_columnconfigure(1, weight=1)

        # ---- Группа 2: Настройки отображения ----
        group2 = ttk.LabelFrame(self.frame_left, text="Настройки отображения", padding="5")
        group2.pack(fill=tk.X, pady=2)

        row = 0
        ttk.Label(group2, text="Режим отображения:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.plot_mode_cb = ttk.Combobox(group2,
                                         values=["Линии+точки", "Только линии", "Только точки"],
                                         state="readonly",
                                         textvariable=self.plot_mode)
        self.plot_mode_cb.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.plot_mode_cb.bind("<<ComboboxSelected>>", lambda e: self.update_settings())
        row += 1

        ttk.Label(group2, text="Толщина линий/точек:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.line_width_scale = tk.Scale(group2, from_=0.5, to=5.0, resolution=0.5,
                                         orient=tk.HORIZONTAL, variable=self.line_width,
                                         command=lambda e: self.update_settings())
        self.line_width_scale.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.line_width_scale.set(1.0)
        row += 1

        ttk.Label(group2, text="Макс значение на графике:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.max_vert_entry = ttk.Entry(group2)
        self.max_vert_entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.max_vert_entry.insert(0, "4000")
        self.max_vert_entry.bind("<KeyRelease>", lambda e: self.update_settings())
        row += 1

        self.auto_cb = ttk.Checkbutton(group2, text="Авто режим",
                                       variable=self.auto_mode,
                                       command=self.toggle_auto_mode)
        self.auto_cb.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        row += 1

        self.start_stop_button = ttk.Button(group2, text="Start", command=self.toggle_accept, state="disabled")
        self.start_stop_button.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        row += 1

        self.clear_button = ttk.Button(group2, text="Очистить график", command=self.clear_graph)
        self.clear_button.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        row += 1
        group2.grid_columnconfigure(1, weight=1)

        # ---- Группа 3: Управление устройством ----
        group3 = ttk.LabelFrame(self.frame_left, text="Управление устройством", padding="5")
        group3.pack(fill=tk.X, pady=2)

        row = 0
        ttk.Label(group3, text="Период обновления (мс):").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.post_pause_entry = ttk.Entry(group3)
        self.post_pause_entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.post_pause_entry.insert(0, "1000")
        self.post_pause_btn = ttk.Button(group3, text="Установить", command=self.send_post_pause)
        self.post_pause_btn.grid(row=row, column=2, padx=5, pady=5)
        row += 1

        ttk.Label(group3, text="Выборок на кадр:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.samples_entry = ttk.Entry(group3)
        self.samples_entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.samples_entry.insert(0, "500")
        self.samples_btn = ttk.Button(group3, text="Установить", command=self.send_samples_per_batch)
        self.samples_btn.grid(row=row, column=2, padx=5, pady=5)
        row += 1

        ttk.Label(group3, text="f выборок (Гц):").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.sample_rate_entry = ttk.Entry(group3)
        self.sample_rate_entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.sample_rate_entry.insert(0, "1000")
        self.sample_rate_btn = ttk.Button(group3, text="Установить", command=self.send_sample_rate)
        self.sample_rate_btn.grid(row=row, column=2, padx=5, pady=5)
        row += 1

        ttk.Separator(group3, orient='horizontal').grid(row=row, column=0, columnspan=3, sticky=tk.EW, pady=5)
        row += 1

        # ---- Выпадающий список для фильтров ----
        ttk.Label(group3, text="Фильтр:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.filter_var = tk.StringVar(value="нет фильтра")
        self.filter_combo = ttk.Combobox(group3, state="readonly",
                                         values=["нет фильтра", "EMA", "AVG", "MED"],
                                         textvariable=self.filter_var)
        self.filter_combo.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.filter_combo.bind("<<ComboboxSelected>>", self.on_filter_changed)
        row += 1

        # Поле для ввода параметра фильтра и кнопка "Установить"
        self.filter_label = ttk.Label(group3, text="Параметр:")
        self.filter_label.grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.filter_entry = ttk.Entry(group3)
        self.filter_entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.filter_entry.insert(0, "0.1")
        self.filter_btn = ttk.Button(group3, text="Установить", command=self.filter_apply)
        self.filter_btn.grid(row=row, column=2, padx=5, pady=5)
        row += 1

        ttk.Separator(group3, orient='horizontal').grid(row=row, column=0, columnspan=3, sticky=tk.EW, pady=5)
        row += 1

        # ---- Выпадающий список для калибровки ----
        ttk.Label(group3, text="Калибровка:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.cal_var = tk.StringVar(value="нет")
        self.cal_combo = ttk.Combobox(group3, state="readonly",
                                      values=["нет", "вкл", "вкл имитация помех"],
                                      textvariable=self.cal_var)
        self.cal_combo.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.cal_combo.bind("<<ComboboxSelected>>", self.on_cal_changed)
        row += 1

        ttk.Separator(group3, orient='horizontal').grid(row=row, column=0, columnspan=3, sticky=tk.EW, pady=5)
        row += 1

        # ---- Выпадающий список для типа вывода ----
        ttk.Label(group3, text="Тип вывода:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.out_var = tk.StringVar(value="N")
        self.out_combo = ttk.Combobox(group3, state="readonly",
                                      values=["mV", "N"],
                                      textvariable=self.out_var)
        self.out_combo.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.out_combo.bind("<<ComboboxSelected>>", self.on_out_changed)
        row += 1

        group3.grid_columnconfigure(1, weight=1)

        self.frame_left.grid_rowconfigure(10, weight=1)

        self.toggle_auto_mode()
        self.update_filter_state()

    # ---------- Обработчики выпадающих списков ----------
    def on_filter_changed(self, event=None):
        self.update_filter_state()

    def update_filter_state(self):
        filter_type = self.filter_var.get()
        if filter_type == "нет фильтра":
            self.filter_entry.config(state="disabled")
            self.filter_label.config(text="Параметр:")
            self.filter_entry.delete(0, tk.END)
            self.filter_entry.insert(0, "")
        elif filter_type == "EMA":
            self.filter_entry.config(state="normal")
            self.filter_label.config(text="alfa coef:")
            if not self.filter_entry.get():
                self.filter_entry.insert(0, "0.1")
        elif filter_type == "AVG":
            self.filter_entry.config(state="normal")
            self.filter_label.config(text="samples:")
            if not self.filter_entry.get():
                self.filter_entry.insert(0, "5")
        elif filter_type == "MED":
            self.filter_entry.config(state="disabled")
            self.filter_label.config(text="Параметр:")
            self.filter_entry.delete(0, tk.END)
            self.filter_entry.insert(0, "3")

    def filter_apply(self):
        filter_type = self.filter_var.get()
        if filter_type == "нет фильтра":
            self.send_command("Filter = 0")
        elif filter_type == "EMA":
            val = self.filter_entry.get().strip()
            try:
                alpha = float(val)
                if not (0 < alpha < 1):
                    raise ValueError
            except ValueError:
                messagebox.showerror("Ошибка", "Введите число от 0 до 1 (например, 0.1)")
                return
            self.send_command("Filter = 1")
            self.send_command(f"EMA alpha = {alpha}")
        elif filter_type == "AVG":
            val = self.filter_entry.get().strip()
            try:
                n = int(val)
                if n <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Ошибка", "Введите положительное целое число")
                return
            self.send_command("Filter = 3")
            self.send_command(f"AVG coef = {n}")
        elif filter_type == "MED":
            self.send_command("Filter = 2")
        else:
            return

    def on_cal_changed(self, event=None):
        cal = self.cal_var.get()
        if cal == "нет":
            self.send_command("Calibration = 0")
        elif cal == "вкл":
            self.send_command("Calibration = 1")
        elif cal == "вкл имитация помех":
            self.send_command("Calibration = 2")

    def on_out_changed(self, event=None):
        out = self.out_var.get()
        if out == "mV":
            self.send_command("OUT = V")
        else:  # "N"
            self.send_command("OUT = N")

    # ---------- Остальные методы без изменений ----------
    def update_port_list(self, event=None):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        current = self.port_list.get()
        self.port_list['values'] = ports
        if current in ports:
            self.port_list.set(current)
        elif ports:
            self.port_list.set(ports[0])
        else:
            self.port_list.set('')

    def toggle_connect(self):
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        port = self.port_list.get()
        if not port:
            messagebox.showerror("Ошибка", "Выберите COM-порт!")
            return
        baud = self.baud_list.get()
        try:
            self.ser = serial.Serial(port=port, baudrate=int(baud), timeout=1, write_timeout=1)
            sleep(1)
            self.is_connected = True
            self.connect_btn.config(text="Disconnect")
            self.serial_port = port
            self.serial_thread = threading.Thread(target=self.read_serial_data, daemon=True)
            self.serial_thread.start()
            self.start_stop_button.config(state="normal")
            print(f"Подключено к {port}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось подключиться: {str(e)}")
            if self.ser:
                self.ser.close()
                self.ser = None
            self.is_connected = False

    def disconnect(self):
        self.is_connected = False
        self.is_accepting = False
        self.start_stop_button.config(text="Start")
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except:
                pass
        self.ser = None
        self.connect_btn.config(text="Connect")
        self.start_stop_button.config(state="disabled")
        print("Отключено от порта")

    def toggle_accept(self):
        if not self.is_connected:
            messagebox.showerror("Ошибка", "Сначала подключитесь к порту!")
            return
        if self.is_accepting:
            self.is_accepting = False
            self.start_stop_button.config(text="Start")
            print("Приём данных остановлен")
        else:
            self.data.clear()
            self.line_names.clear()
            self.lines.clear()
            self.clear_graph()
            self.is_accepting = True
            self.start_stop_button.config(text="Stop")
            print("Приём данных запущен")

    def read_serial_data(self):
        while self.is_connected and self.ser and self.ser.is_open:
            try:
                if self.ser.in_waiting:
                    raw_data = self.ser.read(self.ser.in_waiting)
                    try:
                        decoded = raw_data.decode('utf-8', errors='replace')
                        if self.show_raw_data:
                            cleaned = re.sub(r'[\r\n]+', ' ', decoded)
                            print(f"[Данные {self.data_counter}]: {cleaned.strip()}")
                            self.data_counter += 1
                        else:
                            lines = decoded.splitlines()
                            for line in lines:
                                if line.strip() and '|' not in line:
                                    print(f"[Сообщение] {line.strip()}")
                        self.buffer += decoded
                        while '\n' in self.buffer or '\r' in self.buffer:
                            line, sep, self.buffer = self.buffer.partition('\n')
                            if not sep:
                                line, sep, self.buffer = self.buffer.partition('\r')
                            line = line.strip()
                            if line:
                                self.process_data_line(line)
                    except Exception as e:
                        print(f"Ошибка декодирования: {e}")
            except serial.SerialException as e:
                print(f"Ошибка порта: {e}")
                self.master.after(0, self.disconnect)
                messagebox.showerror("Ошибка", f"Ошибка порта: {e}")
                break
            except Exception as e:
                print(f"Ошибка: {e}")
                self.master.after(0, self.disconnect)
                break
            sleep(0.001)

    def process_data_line(self, line):
        if not self.is_accepting:
            return
        try:
            if line.upper() == "|PLOT_RST|":
                print("[Парсер] |PLOT_RST|")
                self.data.clear()
                self.line_names.clear()
                self.lines.clear()
                self.user_zoom = False
                self.master.after(0, self.clear_graph)
                return
            if line.upper() == "|PLOT_END|":
                print("[Парсер] |PLOT_END|")
                self.master.after(0, self.finalize_frame)
                return
            if '|' not in line or '=' not in line:
                return
            match = re.search(r'\|(.*?)\|', line)
            if not match:
                return
            inner = match.group(1).strip()
            parts = inner.split(',')
            for part in parts:
                part = part.strip()
                if '=' not in part:
                    continue
                name_val = part.split('=', 1)
                if len(name_val) != 2:
                    continue
                name = name_val[0].strip()
                val_str = name_val[1].strip()
                try:
                    value = float(val_str)
                except ValueError:
                    continue
                if name not in self.data:
                    self.data[name] = []
                    if name not in self.line_names:
                        self.line_names.append(name)
                self.data[name].append(value)
        except Exception as e:
            print(f"[Парсер] Ошибка: {e}")

    def finalize_frame(self):
        if not self.data:
            return
        self.update_settings()
        self._perform_update(keep_data=True)
        self.data.clear()
        self.line_names.clear()
        self.lines.clear()

    def send_samples_per_batch(self):
        val = self.samples_entry.get().strip()
        try:
            n = int(val)
            if n <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Введите положительное целое число!")
            return
        self.samples_per_batch = n
        self.update_settings()
        self.send_command(f"samplesPerBatch = {n}")

    def send_sample_rate(self):
        val = self.sample_rate_entry.get().strip()
        try:
            n = int(val)
            if n <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Введите положительное целое число!")
            return
        self.sample_rate = n
        self.update_settings()
        self.send_command(f"sampleRate = {n}")

    def send_post_pause(self):
        val = self.post_pause_entry.get().strip()
        try:
            n = int(val)
            if n < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Введите неотрицательное целое число!")
            return
        self.post_pause = n
        self.send_command(f"postPause = {n}")

    def send_command(self, cmd):
        if not self.is_connected or not self.ser or not self.ser.is_open:
            messagebox.showerror("Ошибка", "Порт не подключён!")
            return
        try:
            if not cmd.endswith(('\n', '\r')):
                cmd += '\r\n'
            self.ser.write(cmd.encode('utf-8'))
            self.ser.flush()
            print(f"Отправлено: {cmd.strip()}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка отправки: {str(e)}")

    def update_settings(self):
        if not self.auto_mode.get():
            try:
                vert_val = self.max_vert_entry.get().strip()
                if vert_val.lower() == "нет" or vert_val == "":
                    self.max_points_vertical = None
                else:
                    self.max_points_vertical = float(vert_val)
                    if self.max_points_vertical < 0:
                        self.max_points_vertical = None
            except ValueError:
                self.max_points_vertical = 4000

            try:
                spb = int(self.samples_entry.get())
                self.samples_per_batch = spb if spb > 0 else 500
            except:
                self.samples_per_batch = 500

            try:
                sr = int(self.sample_rate_entry.get())
                self.sample_rate = sr if sr > 0 else 1000
            except:
                self.sample_rate = 1000

            try:
                pp = int(self.post_pause_entry.get())
                self.post_pause = pp if pp >= 0 else 1000
            except:
                self.post_pause = 1000
        else:
            self.max_points_vertical = None
            self.samples_per_batch = 500

        if self.data and self.is_accepting:
            self._perform_update()

    def _perform_update(self, keep_data=False):
        if not self.data:
            return

        if self.user_zoom:
            xlim = self.ax.get_xlim()
            ylim = self.ax.get_ylim()

        for name in list(self.lines.keys()):
            if name not in self.data or not self.data[name]:
                self.lines[name].remove()
                del self.lines[name]

        mode = self.plot_mode.get()
        lw = self.line_width.get()
        if mode == "Линии+точки":
            linestyle = '-'
            marker = 'o'
            markersize = lw * 2
        elif mode == "Только линии":
            linestyle = '-'
            marker = ''
            markersize = 0
        else:
            linestyle = 'none'
            marker = 'o'
            markersize = lw * 3

        auto = self.auto_mode.get()

        for name, values in self.data.items():
            if not values:
                continue
            if auto:
                display_values = values
            else:
                display_values = values[-self.samples_per_batch:] if self.samples_per_batch else values

            n = len(display_values)
            if n == 0:
                continue

            if auto:
                x_axis = range(n)
            else:
                rate = self.sample_rate
                total_time_ms = (self.samples_per_batch / rate) * 1000 if rate > 0 else self.samples_per_batch
                if n > 1:
                    x_axis = np.linspace(0, total_time_ms, n)
                else:
                    x_axis = [0]

            if name in self.lines:
                self.lines[name].set_data(x_axis, display_values)
                self.lines[name].set_linestyle(linestyle)
                self.lines[name].set_marker(marker)
                self.lines[name].set_linewidth(lw)
                self.lines[name].set_markersize(markersize)
            else:
                line, = self.ax.plot(x_axis, display_values, label=name,
                                     linestyle=linestyle, marker=marker,
                                     linewidth=lw, markersize=markersize)
                self.lines[name] = line

        if self.lines:
            self.ax.legend(fontsize=8)
        else:
            if self.ax.legend_ is not None:
                self.ax.legend_.remove()

        self.ax.grid(True)

        if auto:
            self.ax.set_xlabel("Номер точки", fontsize=8)
        else:
            self.ax.set_xlabel("время (мс)", fontsize=8)
        self.ax.set_ylabel("Значение", fontsize=8)
        self.ax.set_title("Данные с COM-порта", fontsize=9)

        if not self.user_zoom:
            if auto:
                self.ax.relim()
                self.ax.autoscale_view()
            else:
                rate = self.sample_rate
                total_time_ms = (self.samples_per_batch / rate) * 1000 if rate > 0 else self.samples_per_batch
                if total_time_ms > 0:
                    self.ax.set_xlim(0, total_time_ms)
                else:
                    self.ax.relim()
                    self.ax.autoscale_view()
                if self.max_points_vertical is not None:
                    self.ax.set_ylim(0, self.max_points_vertical)
                else:
                    self.ax.relim()
                    self.ax.autoscale_view()
        else:
            self.ax.set_xlim(xlim)
            self.ax.set_ylim(ylim)

        self.canvas.draw_idle()

    # ---------- Панорамирование и зум ----------
    def on_scroll(self, event):
        if event.inaxes != self.ax:
            return
        self.user_zoom = True
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        xdata = event.xdata
        ydata = event.ydata
        if event.button == 'up':
            scale_factor = 0.9
        else:
            scale_factor = 1.1
        new_xlim = [xdata - (xdata - xlim[0]) * scale_factor,
                    xdata + (xlim[1] - xdata) * scale_factor]
        new_ylim = [ydata - (ydata - ylim[0]) * scale_factor,
                    ydata + (ylim[1] - ydata) * scale_factor]
        self.ax.set_xlim(new_xlim)
        self.ax.set_ylim(new_ylim)
        self.canvas.draw_idle()

    def on_press(self, event):
        if event.button == 2 and event.xdata is not None and event.ydata is not None:
            self.is_panning = True
            self.pan_start_x = event.xdata
            self.pan_start_ydata = event.ydata
            self.pan_start_xlim = self.ax.get_xlim()
            self.pan_start_ylim = self.ax.get_ylim()

    def on_release(self, event):
        if event.button == 2:
            self.is_panning = False

    def on_motion(self, event):
        if self.is_panning and event.xdata is not None and event.ydata is not None:
            dx = event.xdata - self.pan_start_x
            dy = event.ydata - self.pan_start_ydata
            new_xlim = [self.pan_start_xlim[0] - dx, self.pan_start_xlim[1] - dx]
            new_ylim = [self.pan_start_ylim[0] - dy, self.pan_start_ylim[1] - dy]
            self.ax.set_xlim(new_xlim)
            self.ax.set_ylim(new_ylim)
            self.canvas.draw_idle()

    # ---------- Очистка ----------
    def clear_graph(self):
        self.data.clear()
        self.line_names.clear()
        for line in self.lines.values():
            line.remove()
        self.lines.clear()
        self.user_zoom = False
        self.ax.clear()
        self.ax.grid(True)
        self.ax.set_xlabel("Номер точки", fontsize=8)
        self.ax.set_ylabel("Значение", fontsize=8)
        self.ax.set_title("Данные с COM-порта", fontsize=9)
        self.canvas.draw()

    def send_data(self):
        if not self.is_connected or not self.ser or not self.ser.is_open:
            messagebox.showerror("Ошибка", "Порт не подключён!")
            return
        data = self.send_entry.get().strip()
        if not data:
            return
        try:
            if not data.endswith(('\n', '\r')):
                data += '\r\n'
            self.ser.write(data.encode('utf-8'))
            self.ser.flush()
            self.send_entry.delete(0, tk.END)
            print(f"Отправлено: {data.strip()}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка отправки: {str(e)}")

    def toggle_raw_data(self):
        self.show_raw_data = self.raw_data_var.get()

    def toggle_auto_mode(self):
        auto = self.auto_mode.get()
        widgets = [
            self.samples_entry, self.samples_btn,
            self.max_vert_entry,
            self.sample_rate_entry, self.sample_rate_btn,
            self.post_pause_entry, self.post_pause_btn
        ]
        state = "disabled" if auto else "normal"
        for w in widgets:
            w.config(state=state)
        if self.data and self.is_accepting:
            self._perform_update()


if __name__ == "__main__":
    root = tk.Tk()
    window_width = 950
    window_height = 750
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width // 2) - (window_width // 2)
    y = (screen_height // 2) - (window_height // 2)
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")

    app = SerialPlotter(root)

    def on_closing():
        app.disconnect()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()