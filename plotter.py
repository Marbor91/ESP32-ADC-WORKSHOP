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

class SerialPlotter:
    def __init__(self, master):
        self.master = master
        master.title("График данных с COM-порта")

        # Проверка прав администратора
        if os.name == 'nt' and not ctypes.windll.shell32.IsUserAnAdmin():
            messagebox.showerror("Ошибка", "Запустите программу от имени администратора!")
            sys.exit(1)

        # Оптимизация графики
        plt.rcParams['path.simplify'] = True
        plt.rcParams['path.simplify_threshold'] = 1.0
        plt.rcParams['lines.antialiased'] = False
        plt.rcParams['backend'] = 'TkAgg'

        # Переменные
        self.is_running = False
        self.serial_port = None
        self.ser = None
        self.data = {}
        self.line_names = []
        self.max_points_horizontal = 500  # Уменьшено для скорости
        self.max_points_vertical = None
        self.buffer = ""
        self.serial_thread = None
        self.last_plot_time = 0
        self.plot_interval = 0
        self.show_raw_data = False
        self.data_counter = 0
        self._plot_pending = False

        # Настройка GUI
        self.create_widgets()

        # Инициализация графика
        self.figure, self.ax = plt.subplots(figsize=(8, 4), dpi=100)
        self.figure.set_facecolor('#f0f0f0')
        self.ax.set_facecolor('#f0f0f0')
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.master)
        self.canvas.get_tk_widget().grid(row=10, column=0, columnspan=2, sticky=tk.NSEW, padx=5, pady=5)
        self.ax.grid(True)
        self.clear_graph()

    def create_widgets(self):
        style = ttk.Style()
        style.configure('TButton', padding=5)
        style.configure('TCheckbutton', padding=5)

        # COM-порт
        ttk.Label(self.master, text="COM-порт:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.port_list = ttk.Combobox(self.master, state="readonly")
        self.port_list.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        self.update_port_list()
        self.port_list.bind("<<ComboboxSelected>>", self.on_port_selected)

        # Скорость порта
        ttk.Label(self.master, text="Скорость (бод):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.baud_list = ttk.Combobox(self.master, 
                                    values=[9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600],
                                    state="readonly")
        self.baud_list.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)
        self.baud_list.set(921600)

        # Настройки графика
        ttk.Label(self.master, text="Макс. точек:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.max_horiz_entry = ttk.Entry(self.master)
        self.max_horiz_entry.insert(0, "500")
        self.max_horiz_entry.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)

        ttk.Label(self.master, text="Макс. значение:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.max_vert_entry = ttk.Entry(self.master)
        self.max_vert_entry.insert(0, "нет")
        self.max_vert_entry.grid(row=3, column=1, sticky=tk.EW, padx=5, pady=5)

        # Режим отрисовки
        ttk.Label(self.master, text="Режим отрисовки:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.plot_mode = ttk.Combobox(self.master, 
                                     values=["Реальное время", "30 раз/сек"],
                                     state="readonly")
        self.plot_mode.set("Реальное время")
        self.plot_mode.grid(row=4, column=1, sticky=tk.EW, padx=5, pady=5)

        # Чекбокс для сырых данных
        self.raw_data_var = tk.BooleanVar()
        self.raw_data_cb = ttk.Checkbutton(self.master, text="Показывать сырые данные",
                                          variable=self.raw_data_var,
                                          command=self.toggle_raw_data)
        self.raw_data_cb.grid(row=5, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)

        # Кнопки управления
        self.start_stop_button = ttk.Button(self.master, text="Запустить", command=self.toggle_start_stop)
        self.start_stop_button.grid(row=6, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)

        self.clear_button = ttk.Button(self.master, text="Очистить график", command=self.clear_graph)
        self.clear_button.grid(row=7, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)

        # Отправка данных
        ttk.Label(self.master, text="Отправить данные:").grid(row=8, column=0, sticky=tk.W, padx=5, pady=5)
        self.send_entry = ttk.Entry(self.master)
        self.send_entry.grid(row=8, column=1, sticky=tk.EW, padx=5, pady=5)
        self.send_entry.bind("<Return>", lambda event: self.send_data())

        self.send_button = ttk.Button(self.master, text="Отправить", command=self.send_data)
        self.send_button.grid(row=9, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)

        # Настройка размеров
        self.master.grid_columnconfigure(1, weight=1)
        self.master.grid_rowconfigure(10, weight=1)
        self.master.minsize(500, 700)

    def toggle_raw_data(self):
        self.show_raw_data = self.raw_data_var.get()

    def update_port_list(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_list['values'] = ports
        if ports:
            self.port_list.set(ports[0])

    def on_port_selected(self, event):
        self.serial_port = self.port_list.get()

    def toggle_start_stop(self):
        if self.is_running:
            self.stop_serial()
        else:
            self.start_serial()

    def start_serial(self):
        if not self.serial_port:
            messagebox.showerror("Ошибка", "Выберите COM-порт!")
            return
        
        try:
            self.max_points_horizontal = int(self.max_horiz_entry.get())
            max_vert = self.max_vert_entry.get()
            self.max_points_vertical = None if max_vert.lower() == "нет" else float(max_vert)
            
            if self.plot_mode.get() == "30 раз/сек":
                self.plot_interval = 1/30
            else:
                self.plot_interval = 0
                
        except ValueError as e:
            messagebox.showerror("Ошибка", f"Некорректное значение: {str(e)}")
            return

        try:
            self.ser = serial.Serial(
                port=self.serial_port,
                baudrate=int(self.baud_list.get()),
                timeout=1,
                write_timeout=1
            )
            sleep(1)
            
            self.is_running = True
            self.start_stop_button.config(text="Остановить")
            self.data = {}
            self.line_names = []
            self.buffer = ""
            self.data_counter = 0
            self.clear_graph()
            
            self.serial_thread = threading.Thread(target=self.read_serial_data, daemon=True)
            self.serial_thread.start()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка открытия порта: {str(e)}")
            if hasattr(self, 'ser') and self.ser:
                self.ser.close()
            self.ser = None

    def stop_serial(self):
        self.is_running = False
        
        if hasattr(self, 'serial_thread') and self.serial_thread:
            self.serial_thread.join(timeout=1)
        
        if hasattr(self, 'ser') and self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except:
                pass
            self.ser = None
        
        self.start_stop_button.config(text="Запустить")

    def read_serial_data(self):
        while self.is_running and self.ser and self.ser.is_open:
            try:
                if self.ser.in_waiting:
                    raw_data = self.ser.read(self.ser.in_waiting)
                    try:
                        decoded = raw_data.decode('utf-8', errors='replace')
                        
                        if self.show_raw_data:
                            cleaned = re.sub(r'[\r\n]+', ' ', decoded)
                            print(f"[Данные {self.data_counter}]: {cleaned.strip()}")
                            self.data_counter += 1
                            
                        self.buffer += decoded
                        
                        while '\n' in self.buffer or '\r' in self.buffer:
                            line, sep, self.buffer = self.buffer.partition('\n')
                            if not sep:
                                line, sep, self.buffer = self.buffer.partition('\r')
                            
                            if line := line.strip():
                                self.process_data_line(line)
                                
                    except Exception as e:
                        print(f"Ошибка декодирования: {e}")
                        
            except serial.SerialException as e:
                print(f"Ошибка порта: {e}")
                self.master.after(0, self.stop_serial)
                self.master.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка порта: {e}"))
                break
            except Exception as e:
                print(f"Ошибка: {e}")
                self.master.after(0, self.stop_serial)
                break
                
            sleep(0.001)

    def process_data_line(self, line):
        try:
            line = re.sub(r'[^\x20-\x7E]+', ' ', line).strip()
            parts = line.split()
            
            if len(parts) >= 4 and len(parts) % 2 == 0:
                need_update = False
                for i in range(0, len(parts), 2):
                    name = parts[i]
                    try:
                        value = float(parts[i+1])
                        if self.max_points_vertical is not None:
                            value = max(min(value, self.max_points_vertical), -self.max_points_vertical)
                            
                        if name not in self.data:
                            self.data[name] = []
                            if name not in self.line_names:
                                self.line_names.append(name)
                                need_update = True
                        
                        self.data[name].append(value)
                        if len(self.data[name]) > self.max_points_horizontal:
                            self.data[name].pop(0)
                            
                        need_update = True
                            
                    except ValueError:
                        continue
                
                if need_update:
                    if self.plot_interval == 0:
                        if not self._plot_pending:
                            self._delayed_update()
                    else:
                        current_time = time()
                        if (current_time - self.last_plot_time) >= self.plot_interval:
                            self._delayed_update()
                            self.last_plot_time = current_time
                
        except Exception as e:
            print(f"Ошибка обработки данных: {e}")

    def _delayed_update(self):
        self._plot_pending = True
        self.master.after(10, self._perform_update)

    def _perform_update(self):
        self._plot_pending = False
        if not self.data:
            return
            
        self.ax.clear()
        
        for name, values in self.data.items():
            if values:
                self.ax.plot(values, label=name)
        
        if self.data:
            self.ax.legend(fontsize=8)
            self.ax.grid(True)
        
        self.ax.set_xlabel("Номер точки", fontsize=8)
        self.ax.set_ylabel("Значение", fontsize=8)
        self.ax.set_title("Данные с COM-порта", fontsize=9)
        
        if self.max_points_vertical is not None:
            self.ax.set_ylim(-self.max_points_vertical, self.max_points_vertical)
        
        self.figure.tight_layout(pad=0.3)
        self.canvas.draw_idle()

    def clear_graph(self):
        self.data.clear()
        self.line_names.clear()
        self.ax.clear()
        self.ax.grid(True)
        self.ax.set_xlabel("Номер точки", fontsize=8)
        self.ax.set_ylabel("Значение", fontsize=8)
        self.ax.set_title("Данные с COM-порта", fontsize=9)
        self.canvas.draw()

    def send_data(self):
        if not self.serial_port:
            messagebox.showerror("Ошибка", "Выберите COM-порт!")
            return
            
        data = self.send_entry.get().strip()
        if not data:
            return
            
        if not hasattr(self, 'ser') or not self.ser or not self.ser.is_open:
            messagebox.showerror("Ошибка", "Порт не открыт!")
            return

        try:
            if not data.endswith(('\n', '\r')):
                data += '\r\n'
                
            self.ser.write(data.encode('utf-8'))
            self.ser.flush()
            self.send_entry.delete(0, tk.END)
            print(f"Отправлено: {data.strip()}")
            
        except serial.SerialTimeoutException:
            messagebox.showerror("Ошибка", "Таймаут отправки!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка отправки: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    
    # Центрирование окна
    window_width = 600
    window_height = 750
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width // 2) - (window_width // 2)
    y = (screen_height // 2) - (window_height // 2)
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    app = SerialPlotter(root)
    
    def on_closing():
        app.stop_serial()
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()