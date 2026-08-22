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

        # Проверка прав администратора (только Windows)
        if os.name == 'nt' and not ctypes.windll.shell32.IsUserAnAdmin():
            messagebox.showerror("Ошибка", "Запустите программу от имени администратора!")
            sys.exit(1)

        # Оптимизация графики для ускорения
        plt.rcParams['path.simplify'] = True
        plt.rcParams['path.simplify_threshold'] = 1.0
        plt.rcParams['lines.antialiased'] = False
        plt.rcParams['backend'] = 'TkAgg'
        plt.rcParams['figure.dpi'] = 80          # Уменьшаем DPI для ускорения

        # ---------- Параметры настройки ----------
        self.max_points_horizontal = 500          # Максимум точек на графике по горизонтали (фикс)
        self.max_points_vertical = 4000           # Максимум по вертикали (фикс, от 0 до max)

        # Переменные состояния
        self.is_running = False              # Флаг работы потока чтения
        self.serial_port = None              # Имя COM-порта
        self.ser = None                      # Объект Serial
        self.data = {}                       # Текущий накапливаемый буфер данных
        self.line_names = []                 # Список имён для отображения в легенде
        self.buffer = ""                     # Буфер для накопления данных из порта
        self.serial_thread = None            # Поток чтения
        self.show_raw_data = False           # Флаг вывода сырых данных в консоль
        self.data_counter = 0                # Счётчик строк для вывода
        self._update_id = None               # ID отложенного обновления для отмены
        self.user_zoom = False               # Флаг, что пользователь приблизил график

        # Параметры отображения
        self.plot_mode = tk.StringVar(value="Линии+точки")  # Режим отображения
        self.line_width = tk.DoubleVar(value=1.0)           # Толщина линий/точек

        # Словарь для хранения объектов линий (для быстрого обновления)
        self.lines = {}

        # Создание интерфейса (расположение: панель управления слева, график справа)
        self.create_widgets()

        # Инициализация графика
        self.figure, self.ax = plt.subplots(figsize=(8, 4), dpi=80)
        self.figure.set_facecolor('#f0f0f0')
        self.ax.set_facecolor('#f0f0f0')
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.frame_right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.ax.grid(True)
        self.clear_graph()

        # Привязка событий мыши для масштабирования колёсиком
        self.canvas.mpl_connect('scroll_event', self.on_scroll)

        # Применяем начальные настройки
        self.update_settings()

    # ---------- Создание виджетов интерфейса ----------
    def create_widgets(self):
        # Основное окно разделено на две колонки: левая (управление) и правая (график)
        self.master.grid_columnconfigure(0, weight=0, minsize=250)  # Левая фиксированной ширины
        self.master.grid_columnconfigure(1, weight=1)               # Правая растягивается
        self.master.grid_rowconfigure(0, weight=1)

        # Левая панель
        self.frame_left = ttk.Frame(self.master, padding="5")
        self.frame_left.grid(row=0, column=0, sticky=tk.N+tk.S+tk.W+tk.E)

        # Правая панель
        self.frame_right = ttk.Frame(self.master)
        self.frame_right.grid(row=0, column=1, sticky=tk.N+tk.S+tk.E+tk.W)

        # Стили
        style = ttk.Style()
        style.configure('TButton', padding=5)
        style.configure('TCheckbutton', padding=5)

        # ---------- Элементы управления (в левой панели) ----------
        row = 0

        # COM-порт
        ttk.Label(self.frame_left, text="COM-порт:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.port_list = ttk.Combobox(self.frame_left, state="readonly")
        self.port_list.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.update_port_list()
        self.port_list.bind("<<ComboboxSelected>>", self.on_port_selected)
        row += 1

        # Скорость порта
        ttk.Label(self.frame_left, text="Скорость (бод):").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.baud_list = ttk.Combobox(self.frame_left,
                                    values=[9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600],
                                    state="readonly")
        self.baud_list.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.baud_list.set(115200)
        row += 1

        # Макс. точек (горизонталь)
        ttk.Label(self.frame_left, text="Макс. точек:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.max_horiz_entry = ttk.Entry(self.frame_left)
        self.max_horiz_entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.max_horiz_entry.insert(0, "500")
        self.max_horiz_entry.bind("<KeyRelease>", lambda e: self.update_settings())
        row += 1

        # Макс. значение (вертикаль)
        ttk.Label(self.frame_left, text="Макс. значение:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.max_vert_entry = ttk.Entry(self.frame_left)
        self.max_vert_entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.max_vert_entry.insert(0, "4000")
        self.max_vert_entry.bind("<KeyRelease>", lambda e: self.update_settings())
        row += 1

        # Режим отображения (выпадающий список)
        ttk.Label(self.frame_left, text="Режим отображения:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.plot_mode_cb = ttk.Combobox(self.frame_left,
                                         values=["Линии+точки", "Только линии", "Только точки"],
                                         state="readonly",
                                         textvariable=self.plot_mode)
        self.plot_mode_cb.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.plot_mode_cb.bind("<<ComboboxSelected>>", lambda e: self.update_settings())
        row += 1

        # Ползунок толщины линий/точек
        ttk.Label(self.frame_left, text="Толщина линий/точек:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.line_width_scale = tk.Scale(self.frame_left, from_=0.5, to=5.0, resolution=0.5,
                                         orient=tk.HORIZONTAL, variable=self.line_width,
                                         command=lambda e: self.update_settings())
        self.line_width_scale.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.line_width_scale.set(1.0)
        row += 1

        # Чекбокс показа сырых данных
        self.raw_data_var = tk.BooleanVar()
        self.raw_data_cb = ttk.Checkbutton(self.frame_left, text="Показывать сырые данные",
                                          variable=self.raw_data_var,
                                          command=self.toggle_raw_data)
        self.raw_data_cb.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        row += 1

        # Кнопки управления
        self.start_stop_button = ttk.Button(self.frame_left, text="Запустить", command=self.toggle_start_stop)
        self.start_stop_button.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        row += 1

        self.clear_button = ttk.Button(self.frame_left, text="Очистить график", command=self.clear_graph)
        self.clear_button.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        row += 1

        self.reset_zoom_button = ttk.Button(self.frame_left, text="Сбросить масштаб", command=self.reset_zoom)
        self.reset_zoom_button.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        row += 1

        # Отправка данных
        ttk.Label(self.frame_left, text="Отправить данные:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.send_entry = ttk.Entry(self.frame_left)
        self.send_entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        self.send_entry.bind("<Return>", lambda event: self.send_data())
        row += 1

        self.send_button = ttk.Button(self.frame_left, text="Отправить", command=self.send_data)
        self.send_button.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        row += 1

        # Растягивание колонок в левой панели
        self.frame_left.grid_columnconfigure(1, weight=1)
        self.frame_left.grid_rowconfigure(row, weight=1)

    # ---------- События для чекбокса ----------
    def toggle_raw_data(self):
        self.show_raw_data = self.raw_data_var.get()

    # ---------- Обновление списка портов ----------
    def update_port_list(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_list['values'] = ports
        if ports:
            self.port_list.set(ports[0])

    def on_port_selected(self, event):
        self.serial_port = self.port_list.get()

    # ---------- Управление запуском/остановкой ----------
    def toggle_start_stop(self):
        if self.is_running:
            self.stop_serial()
        else:
            self.start_serial()

    # ---------- Запуск чтения ----------
    def start_serial(self):
        if not self.serial_port:
            messagebox.showerror("Ошибка", "Выберите COM-порт!")
            return

        # Обновляем настройки
        self.update_settings()

        # Открытие порта
        try:
            self.ser = serial.Serial(
                port=self.serial_port,
                baudrate=int(self.baud_list.get()),
                timeout=1,
                write_timeout=1
            )
            sleep(1)  # Даём время на инициализацию

            self.is_running = True
            self.start_stop_button.config(text="Остановить")
            # Очищаем старые данные
            self.data = {}
            self.line_names = []
            self.lines = {}
            self.buffer = ""
            self.data_counter = 0
            self.user_zoom = False
            self.clear_graph()

            # Запускаем поток чтения
            self.serial_thread = threading.Thread(target=self.read_serial_data, daemon=True)
            self.serial_thread.start()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка открытия порта: {str(e)}")
            if hasattr(self, 'ser') and self.ser:
                self.ser.close()
            self.ser = None

    # ---------- Остановка чтения ----------
    def stop_serial(self):
        self.is_running = False

        # Отменяем все отложенные обновления
        if self._update_id is not None:
            self.master.after_cancel(self._update_id)
            self._update_id = None

        if hasattr(self, 'serial_thread') and self.serial_thread:
            self.serial_thread.join(timeout=1)

        if hasattr(self, 'ser') and self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except:
                pass
            self.ser = None

        self.start_stop_button.config(text="Запустить")

    # ---------- Поток чтения данных из порта ----------
    def read_serial_data(self):
        while self.is_running and self.ser and self.ser.is_open:
            try:
                if self.ser.in_waiting:
                    raw_data = self.ser.read(self.ser.in_waiting)
                    try:
                        decoded = raw_data.decode('utf-8', errors='replace')

                        # Если включен вывод сырых данных, печатаем в консоль без управляющих символов
                        if self.show_raw_data:
                            cleaned = re.sub(r'[\r\n]+', ' ', decoded)
                            print(f"[Данные {self.data_counter}]: {cleaned.strip()}")
                            self.data_counter += 1

                        # Добавляем в буфер
                        self.buffer += decoded

                        # Извлекаем полные строки (разделители \n или \r)
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
                self.master.after(0, self.stop_serial)
                self.master.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка порта: {e}"))
                break
            except Exception as e:
                print(f"Ошибка: {e}")
                self.master.after(0, self.stop_serial)
                break

            sleep(0.001)

    # ---------- Парсер строки данных (новый формат + команды) ----------
    def process_data_line(self, line):
        """
        Парсит строку вида:  |Before = N , After= M|  (или с любым числом пар)
        Обрабатывает команды:
          |PLOT_RST|  – сброс графика (очистка данных)
          |PLOT_END|  – завершение кадра – отрисовка накопленных данных
        """
        try:
            # ---- Команда сброса графика ----
            if line.upper() == "|PLOT_RST|":
                print("[Парсер] Получена команда сброса графика |PLOT_RST|")
                # Очищаем данные и график
                self.data.clear()
                self.line_names.clear()
                self.lines.clear()
                self.user_zoom = False
                self.master.after(0, self.clear_graph)
                return

            # ---- Команда завершения кадра ----
            if line.upper() == "|PLOT_END|":
                print("[Парсер] Получена команда |PLOT_END| – отрисовка кадра")
                # Отрисовываем текущий накопленный кадр и затем очищаем данные для нового
                self.master.after(0, self.finalize_frame)
                return

            # ---- Обычный парсинг данных (если не команда) ----
            if '|' not in line or '=' not in line:
                return

            match = re.search(r'\|(.*?)\|', line)
            if not match:
                return

            inner = match.group(1).strip()
            parts = inner.split(',')
            if len(parts) < 1:
                return

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

                # Инициализируем список для нового имени
                if name not in self.data:
                    self.data[name] = []
                    if name not in self.line_names:
                        self.line_names.append(name)

                # Добавляем значение
                self.data[name].append(value)
                # Ограничиваем длину списка, чтобы не переполнять память (можно хранить все, но отрезать при отрисовке)
                # Оставим неограниченным, отрезаем при отрисовке до max_points_horizontal

        except Exception as e:
            print(f"[Парсер] Ошибка обработки строки '{line}': {e}")

    # ---------- Завершение кадра (отрисовка и очистка) ----------
    def finalize_frame(self):
        """Вызывается при получении |PLOT_END| – отображает накопленные данные и очищает буфер."""
        if not self.data:
            # Если данных нет, ничего не делаем
            return

        # Обновляем настройки (на случай, если пользователь изменил параметры)
        self.update_settings()

        # Отрисовываем кадр
        self._perform_update(keep_data=True)  # не очищаем данные, они будут очищены после отрисовки

        # Очищаем буфер данных для нового кадра
        self.data.clear()
        self.line_names.clear()
        self.lines.clear()   # линии будут пересозданы при следующем кадре

    # ---------- Обновление настроек (при изменении полей/чекбоксов) ----------
    def update_settings(self):
        """Считывает значения полей, обновляет переменные и применяет ограничения к уже имеющимся данным."""
        # Обновляем значения из полей
        try:
            horiz_val = int(self.max_horiz_entry.get())
            self.max_points_horizontal = horiz_val if horiz_val > 0 else 1
        except ValueError:
            self.max_points_horizontal = 500

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

        # Если есть данные, перерисовываем их с новыми настройками
        if self.data:
            self._perform_update()

    # ---------- Отрисовка (основной метод) ----------
    def _perform_update(self, keep_data=False):
        """
        Отрисовывает текущие данные (self.data) с учётом настроек.
        Если keep_data=True, данные не очищаются (используется при финализации кадра,
        но очистка выполняется в finalize_frame).
        """
        if not self.data:
            return

        # Сохраняем пределы, если пользователь приближал
        if self.user_zoom:
            xlim = self.ax.get_xlim()
            ylim = self.ax.get_ylim()

        # Удаляем линии для отсутствующих имён
        for name in list(self.lines.keys()):
            if name not in self.data or not self.data[name]:
                self.lines[name].remove()
                del self.lines[name]

        # Получаем параметры отображения
        mode = self.plot_mode.get()
        lw = self.line_width.get()
        # Определяем стиль линии и маркера
        if mode == "Линии+точки":
            linestyle = '-'
            marker = 'o'
            markersize = lw * 2  # размер точки пропорционален толщине
        elif mode == "Только линии":
            linestyle = '-'
            marker = ''
            markersize = 0
        else:  # "Только точки"
            linestyle = 'none'
            marker = 'o'
            markersize = lw * 3  # размер точки чуть больше

        # Обновляем или создаём линии
        for name, values in self.data.items():
            if not values:
                continue
            # Берём последние self.max_points_horizontal точек
            display_values = values[-self.max_points_horizontal:] if self.max_points_horizontal else values
            x = range(len(display_values))
            if name in self.lines:
                # Обновляем существующую линию
                self.lines[name].set_data(x, display_values)
                self.lines[name].set_linestyle(linestyle)
                self.lines[name].set_marker(marker)
                self.lines[name].set_linewidth(lw)
                self.lines[name].set_markersize(markersize)
            else:
                # Создаём новую линию
                line, = self.ax.plot(x, display_values, label=name,
                                     linestyle=linestyle, marker=marker,
                                     linewidth=lw, markersize=markersize)
                self.lines[name] = line

        # Обновляем легенду (если изменился набор линий)
        if self.lines:
            self.ax.legend(fontsize=8)
        else:
            if self.ax.legend_ is not None:
                self.ax.legend_.remove()

        self.ax.grid(True)

        # Устанавливаем заголовки
        self.ax.set_xlabel("Номер точки", fontsize=8)
        self.ax.set_ylabel("Значение", fontsize=8)
        self.ax.set_title("Данные с COM-порта", fontsize=9)

        # Устанавливаем пределы осей
        if not self.user_zoom:
            if self.max_points_vertical is not None:
                self.ax.set_ylim(0, self.max_points_vertical)
            else:
                self.ax.relim()
                self.ax.autoscale_view()
            # по горизонтали можно оставить авто, либо установить фиксированный диапазон 0..max_points_horizontal
            if self.max_points_horizontal:
                self.ax.set_xlim(0, self.max_points_horizontal)
        else:
            # Восстанавливаем сохранённые пределы
            self.ax.set_xlim(xlim)
            self.ax.set_ylim(ylim)

        # Перерисовываем
        self.canvas.draw_idle()

    # ---------- Отложенное обновление (не используется, оставлено для совместимости) ----------
    def _delayed_update(self):
        pass  # не используется

    # ---------- Обработка прокрутки мыши (масштабирование) ----------
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

    # ---------- Сброс масштаба ----------
    def reset_zoom(self):
        self.user_zoom = False
        if self.data:
            self._perform_update()

    # ---------- Очистка графика и данных ----------
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

    # ---------- Отправка данных в порт ----------
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
    window_width = 950
    window_height = 720
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