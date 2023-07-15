import logging
import tkinter as tk
import sqlite3 as sq
import configparser
import asyncio
import aiohttp
import re
import io
from typing import List
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk


def parse_content(content: str) -> str:
    soup = BeautifulSoup(content, 'html.parser')
    body_content = soup.find(id='bodyContent')
    text = body_content.get_text()
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()


async def get_info_lake(session: aiohttp.ClientSession, url: str, pack_text_field: tk.Text) -> None:
    try:
        async with session.get(url) as connection:
            if connection.status == 200:
                content = await connection.text()
                loop = asyncio.get_running_loop()
                with ThreadPoolExecutor() as pool:
                    task = loop.run_in_executor(
                        pool, parse_content, content
                    )
                    result = await task
                    if pack_text_field.get(0.1, tk.END).strip() == "Введите информацию об озере...":
                        pack_text_field.delete(1.0, tk.END)
                    pack_text_field.configure(foreground='black')
                    pack_text_field.insert(tk.END, result)
            else:
                tk.messagebox.showinfo("Ошибка", "Информации о данном озере нет в википедии")
                pack_text_field.focus_set()
    except aiohttp.ClientConnectionError:
        tk.messagebox.showerror("Ошибка", "Нет сетевого подключения!")


async def get_wikipedia(topic: str, pack_text: tk.Text) -> None:
    url = f'https://ru.wikipedia.org/wiki/{topic}'
    async with aiohttp.ClientSession() as session:
        await get_info_lake(session, url, pack_text)


def connect_to_wikipedia(field: tk.Entry, pack_text: tk.Text) -> None:
    if field.get() != '' and field.get() != "Введите название озера...":
        asyncio.run(get_wikipedia(field.get(), pack_text))
    else:
        tk.messagebox.showerror("Ошибка", "Поле с названием озера не должно быть пустым!")


class App:

    def __init__(self, config_file: str):

        config = configparser.ConfigParser()
        config.read(config_file)

        self.root = tk.Tk()
        self.style = ttk.Style()

        self.DB_NAME = config.get('database', 'database_file')

        self.task = None
        self.image_lake = None
        self.image_lake_refactor = None

        width = int(config.get('app', 'width'))
        height = int(config.get('app', 'height'))

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        x = (screen_width - width) // 2
        y = (screen_height - height) // 2

        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.title("Известные озера России")
        self.style.configure("Close.TButton")

        # LIST_BOX
        self.list_box = tk.Listbox(self.root, selectmode=tk.SINGLE, font=('Arial', 12))
        self.list_box.insert(tk.END, '')
        self.list_of_lakes = self.get_list_of_lakes()
        for option in self.list_of_lakes:
            self.list_box.insert(tk.END, option)
        self.style.configure('Search.TEntry', foreground='grey')
        self.search_entry = ttk.Entry(self.root, style='Search.TEntry', width=100)
        self.search_entry.insert(tk.END, "Поиск...")
        self.search_entry.bind("<FocusIn>", lambda event: (self.hide_text_info(event.widget, "Поиск..."),
                                                           self.root.after(10, self.check_value)))
        self.search_entry.bind('<FocusOut>', lambda event: (self.set_text_info(event.widget, "Поиск..."),
                                                            self.root.after_cancel(self.task)))
        self.search_entry.grid(row=0, column=0, sticky=tk.N)
        self.list_box.grid(row=0, column=0, sticky=tk.NS + tk.EW)
        self.list_box.configure(selectbackground=self.list_box.cget('background'), selectforeground='gray')
        self.list_box.bind("<<ListboxSelect>>", self.on_select)

        # IMAGE
        self.image = None
        self.image_field = tk.Label(self.root)
        self.image_field.grid(row=0, column=1, sticky="nsew")

        # TEXT
        self.text_field = tk.Text(self.root, wrap=tk.WORD)
        self.text_field.grid(row=0, column=2, sticky=tk.NS + tk.EW)
        self.text_field.configure(state="disabled")

        self.root.rowconfigure(0, weight=1, uniform="row")
        self.root.columnconfigure(0, weight=20, uniform="column")
        self.root.columnconfigure(1, weight=55, uniform="column")
        self.root.columnconfigure(2, weight=25, uniform="column")
        self.root.bind("<Configure>", lambda event: self.on_resize(event))

        # MENU1
        menu_bar = tk.Menu(self.root)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label="Фонд", menu=file_menu)
        file_menu.add_command(label="Найти...", command=self.search_lake)
        file_menu.add_separator()
        file_menu.add_command(label="Добавить F2", command=self.add_lake)
        self.root.bind("<F2>", lambda event: self.add_lake())
        file_menu.add_command(label="Удалить F3", command=self.delete_lake_window)
        self.root.bind("<F3>", lambda event: self.delete_lake_window())
        file_menu.add_command(label="Выйти F4", command=self.root.quit)
        self.root.bind("<F4>", lambda event: self.refactor_lake())
        self.root.bind("<F10>", lambda event: file_menu.post(event.x_root, event.y_root))

        # Menu2
        file_menu2 = tk.Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label="Справка", menu=file_menu2)
        file_menu2.add_command(label="Содержание", command=self.help_window)
        self.root.bind("<F1>", lambda event: self.help_window())
        file_menu2.add_separator()
        file_menu2.add_command(label="О программе", command=self.show_modal_window)

        self.root.config(menu=menu_bar)
        self.root.mainloop()

    @staticmethod
    def set_text_info(field: ttk.Entry | tk.Entry, text_info: str):
        if not field.get():
            field.insert(0, text_info)
            field.configure(foreground="#999")

    @staticmethod
    def hide_text_info(field: ttk.Entry | tk.Entry, text_info: str):
        if field.get() == text_info:
            field.delete(0, 'end')
            field.configure(foreground='black')

    def get_list_of_lakes(self) -> List[str]:
        try:
            with sq.connect(self.DB_NAME) as connection:
                cur = connection.cursor()
                list_of_lakes = cur.execute("SELECT name FROM lakes ORDER BY name").fetchall()
                list_of_lakes = [lake[0] for lake in list_of_lakes]
                return list_of_lakes
        except sq.OperationalError as e:
            logging.warning(e)
            tk.messagebox.showerror('Ошибка', 'Нет подключения к базе данных')
            self.root.destroy()

    def update_list_box(self):
        self.list_box.delete(1, tk.END)
        self.list_of_lakes = self.get_list_of_lakes()
        for option in self.list_of_lakes:
            self.list_box.insert(tk.END, option)

    def show_modal_window(self):
        modal_window = tk.Toplevel(name='modal_window')
        self.pack_window(modal_window)
        modal_window.resizable(False, False)
        modal_window.title("О программе")
        image = Image.open('!.jpeg')
        image = image.resize((40, 40))
        picture = ImageTk.PhotoImage(image)
        image_label = tk.Label(modal_window, font=("Arial", 40), padx=10, pady=10, image=picture)
        image_label.grid(row=0, column=0, padx=5, pady=5)
        label_text = tk.Label(modal_window, text="База данных 'Известные озера России'\n"
                                                 "(c) Khalyavka A.D., Russia, 2023\n", padx=10, pady=10)
        label_text.grid(row=0, column=1, padx=5, pady=5)

        close_button = ttk.Button(modal_window, text="Ок", style="Close.TButton", command=modal_window.destroy)
        close_button.grid(row=1, column=1, sticky=tk.E, padx=10, pady=5)

        modal_window.transient(master=self.root)
        modal_window.grab_set()
        modal_window.focus_set()
        self.root.wait_window(modal_window)

    def help_window(self):
        window = tk.Toplevel(name='help_window')
        window.title("Справка")
        window.geometry(f"400x200")
        self.pack_window(window)
        window.resizable(False, False)

        text = "База данных 'Знаменитые озера России'\n" \
               "Позволяет: добавлять/ изменять/ удалять информацию.\n" \
               "Клавиши программы:\n" \
               "F1-вызов справки по программе,\n" \
               "F2-добавить в базу данных,\n" \
               "F3-удалить из базы данных,\n" \
               "F4-изменить запись в базе данных,\n" \
               "F10-меню программы"

        label = tk.Label(window, text=text, font=("Arial", 10))
        label.pack(padx=20, pady=10)

        close_button = ttk.Button(window, text="Закрыть", style="Close.TButton", command=window.destroy)
        close_button.pack(side=tk.RIGHT, padx=20, pady=0)

    def pack_window(self, window: tk.Toplevel) -> (int, int):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()
        x = (screen_width - root_width) // 2
        y = (screen_height - root_height) // 2
        window.geometry(f"+{x + 150}+{y}")
        window.focus_set()

    def change_listbox(self, field: tk.Listbox, text: str) -> None:
        if text != 'Поиск...' and text != '':
            field.delete(1, tk.END)
            for el in self.list_of_lakes:
                if text.lower() in el.lower():
                    field.insert(tk.END, el)
        elif not text:
            field.delete(1, tk.END)
            for el in self.list_of_lakes:
                field.insert(tk.END, el)

    def search_lake(self):
        def search():
            text = entry_search.get()
            self.search_entry.configure(foreground='black')
            self.search_entry.delete(0, tk.END)
            if text != 'Введите название озера...':
                self.search_entry.insert(0, text)
                self.change_listbox(self.list_box, text)
            else:
                self.search_entry.insert(tk.END, '')
            search_window.destroy()

        search_window = tk.Toplevel(name='search_window')
        search_window.title("Поиск")
        self.pack_window(search_window)
        entry_search = ttk.Entry(search_window, width=50)
        entry_search.configure(foreground='#999')
        entry_search.bind("<FocusIn>", lambda event: self.hide_text_info(event.widget, 'Введите название озера...'))
        entry_search.bind('<FocusOut>', lambda event: self.set_text_info(event.widget, 'Введите название озера...'))
        entry_search.insert(0, 'Введите название озера...')
        entry_search.grid(row=0, column=0, columnspan=2)

        search_button = ttk.Button(search_window, text="Найти", command=search, width=25)
        search_button.grid(row=1, column=0, pady=10)
        cancel_button = ttk.Button(search_window, text="Отмена", command=search_window.destroy, width=25)
        cancel_button.grid(row=1, column=1, pady=10)

    def on_resize(self, event: tk.Event) -> None:
        if self.image is None:
            return
        label_width = self.image_field.winfo_width()
        label_height = self.image_field.winfo_height()

        photo = Image.open(io.BytesIO(self.image)).resize((label_width, label_height), Image.BICUBIC)
        picture = ImageTk.PhotoImage(photo)
        self.image_field.configure(image=picture)
        self.image_field.image = picture

    def check_value(self) -> None:
        text = self.search_entry.get()
        self.change_listbox(self.list_box, text)
        self.task = self.root.after(10, self.check_value)

    def on_select(self, event: tk.Event) -> None:
        try:
            widget: tk.Listbox = event.widget
            selection = widget.curselection()
            name = widget.get(selection)
            with sq.connect(self.DB_NAME) as connection:
                cur = connection.cursor()
                image_url, description = cur.execute("SELECT picture, description FROM lakes WHERE name = ?",
                                                     (name,)).fetchone()

        except tk.TclError as e:
            logging.warning(e)
        else:
            self.image = image_url
            self.on_resize(tk.Event())

            self.text_field.configure(state="normal")
            self.text_field.delete(1.0, tk.END)
            self.text_field.insert(tk.END, description)
            self.text_field.configure(state="disabled")

    def delete_lake_window(self):
        del_window = tk.Toplevel(name="delete_window")
        del_window.title('Удаление озера')
        self.pack_window(del_window)
        entry_del_lake = ttk.Entry(del_window, width=50)
        entry_del_lake.configure(foreground='#999')
        entry_del_lake.bind("<FocusIn>", lambda event: self.hide_text_info(event.widget, 'Введите название озера...'))
        entry_del_lake.bind('<FocusOut>', lambda event: self.set_text_info(event.widget, 'Введите название озера...'))
        entry_del_lake.insert(0, 'Введите название озера...')
        entry_del_lake.grid(row=0, column=0, columnspan=2)
        search_button = ttk.Button(del_window, text="Удалить",
                                   command=lambda: self.delete_lake(entry_del_lake.get()),
                                   width=25)
        search_button.grid(row=1, column=0, pady=10)
        cancel_button = ttk.Button(del_window, text="Отмена", command=del_window.destroy, width=25)
        cancel_button.grid(row=1, column=1, pady=10)

    def delete_lake(self, name: str) -> None:
        if name == "Введите название озера..." or name == '':
            messagebox.showerror('Ошибка', 'Поле названия озера не должно быть пустым!')
            return
        if name not in self.list_of_lakes:
            messagebox.showerror('Ошибка', f'Озера с названием {name} не существует в базе')
            return
        with sq.connect(self.DB_NAME) as connection:
            cur = connection.cursor()
            cur.execute("DELETE FROM lakes WHERE name = ?", (name,))
        self.list_of_lakes.remove(name)
        list_box_values = self.list_box.get(0, tk.END)
        for i, value in enumerate(list_box_values):
            if value == name:
                self.list_box.delete(i)
        messagebox.showinfo('Удаление озера', f'"{name}" успешно удалено!')

    @staticmethod
    def clear_entry_text(event: tk.Event):
        field: tk.Text = event.widget
        if field.get(0.1, tk.END).strip() == "Введите информацию об озере...":
            field.delete(1.0, tk.END)
            field.configure(foreground='black')

    @staticmethod
    def set_hint_text(event: tk.Event):
        field: tk.Text = event.widget
        if not field.get(1.0, tk.END).strip():
            field.insert(0.1, "Введите информацию об озере...")
            field.configure(foreground="#999")

    @staticmethod
    def delete_info_about_lake(field: tk.Text, text: str) -> None:
        field.delete(1.0, tk.END)
        field.insert(0.1, text)
        field.configure(foreground="#999")

    @staticmethod
    def delete_name_of_lake(field: tk.Entry, text: str) -> None:
        field.delete(0, tk.END)
        field.insert(0, text)
        field.configure(foreground="#999")

    def open_file_dialog(self, master: tk.Toplevel, field: tk.Button):
        file_path = filedialog.askopenfilename(parent=master, filetypes=[("Image files", "*.jpg;*.png;*.jpeg")])
        if file_path:
            if field.winfo_name() == 'image_save':
                self.image_lake = file_path
            else:
                self.image_lake_refactor = file_path
            image = Image.open(file_path)
            image = image.resize((150, 150))
            photo = ImageTk.PhotoImage(image)
            field.configure(image=photo)
            field.image = photo

    def delete_picture_of_lake(self, field: tk.Button) -> None:
        if field.winfo_name() == 'image_save':
            self.image_lake = None
        else:
            self.image_lake_refactor = None
        base_image = Image.open("default.png")
        picture = base_image.resize((150, 150))
        picture_not_found = ImageTk.PhotoImage(picture)
        field.configure(image=picture_not_found)
        field.image = picture_not_found

    def check_image(self, type_image: int) -> bytes:
        if type_image:
            image = self.image_lake
        else:
            image = self.image_lake_refactor
        if image is not None:
            with open(image, 'rb') as image_file:
                image_data = image_file.read()
        else:
            with open('default.png', 'rb') as image_file:
                image_data = image_file.read()
        return image_data

    def add_lake(self):
        def save_data():
            name_of_lake = lake_name_entry.get()
            if name_of_lake in ('', "Введите название озера..."):
                tk.messagebox.showerror("Ошибка", "Обязательное поле: название озера")
                return
            else:
                try:
                    with sq.connect(self.DB_NAME) as con:
                        cur = con.cursor()
                        image_data = self.check_image(1)
                        text_about_lake = text_field_about_lake.get(1.0, tk.END)
                        if text_about_lake.strip() == 'Введите информацию об озере...':
                            text_about_lake = 'Нет информации'
                        cur.execute("INSERT INTO lakes (name, picture, description) VALUES (?, ?, ?) ",
                                    (name_of_lake, image_data,
                                     text_about_lake))
                except sq.OperationalError as e:
                    logging.warning(e)
                    tk.messagebox.showerror('Ошибка', 'Нет подключения к базе данных')
                    add_form.focus_set()
                except sq.IntegrityError as e:
                    logging.warning(e)
                    tk.messagebox.showerror('Ошибка', f'Озеро с названием {name_of_lake} уже существует в базе данных')
                    add_form.focus_set()
                else:
                    self.update_list_box()
                    messagebox.showinfo('Результат', 'Озеро успешно добавлено в базу')
                    add_form.destroy()

        add_form = tk.Toplevel(name='add_window')
        self.pack_window(add_form)
        add_form.title("Ввод информации о озере")
        add_form.resizable(False, False)

        image = Image.open("default.png")
        image = image.resize((150, 150))
        photo = ImageTk.PhotoImage(image)

        open_file_button = ttk.Button(add_form, text="Обзор...",
                                      command=lambda: self.open_file_dialog(add_form, open_file_button),
                                      image=photo,
                                      name='image_save')
        open_file_button.image = photo
        open_file_button.grid(row=0, column=0, columnspan=2, padx=5, pady=5)
        delete_image = ttk.Button(add_form, text="\u2715",
                                  command=lambda: self.delete_picture_of_lake(open_file_button),
                                  width=2)
        delete_image.grid(row=0, column=1, padx=50, pady=10, sticky=tk.NW)

        lake_name_entry = ttk.Entry(add_form, width=20)
        lake_name_entry.configure(foreground="#999")
        lake_name_entry.insert(0, "Введите название озера...")
        lake_name_entry.bind("<FocusIn>", lambda event: self.hide_text_info(event.widget, "Введите название озера..."))
        lake_name_entry.bind('<FocusOut>', lambda event: self.set_text_info(event.widget, "Введите название озера..."))
        lake_name_entry.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        delete_lake_name = ttk.Button(add_form, text="\u2715",
                                      command=lambda: self.delete_name_of_lake(lake_name_entry,
                                                                               'Введите название озера...'),
                                      width=2)
        delete_lake_name.grid(row=1, column=1, padx=5, pady=10, sticky=tk.NE)

        text_field_about_lake = tk.Text(add_form, width=45, height=5)
        text_field_about_lake.configure(foreground='#999')
        text_field_about_lake.insert(0.1, "Введите информацию об озере...")
        text_field_about_lake.bind("<Control-c>", lambda event: self.text_field.event_generate("<<Copy>>"))
        text_field_about_lake.bind("<FocusIn>", self.clear_entry_text)
        text_field_about_lake.bind('<FocusOut>', self.set_hint_text)
        text_field_about_lake.grid(row=2, column=0, columnspan=2, sticky=tk.S)
        delete_lake_about = ttk.Button(add_form, text="\u2715",
                                       command=lambda: self.delete_info_about_lake(text_field_about_lake,
                                                                                   "Введите информацию об озере..."),
                                       width=2)
        delete_lake_about.grid(row=2, column=1, padx=5, pady=10, sticky=tk.NE)

        button_about_lake = ttk.Button(add_form, text="Взять информацию об озере из википедии",
                                       command=lambda: connect_to_wikipedia(lake_name_entry,
                                                                            text_field_about_lake))
        button_about_lake.grid(row=3, column=0, columnspan=2, padx=5, pady=10)

        save_button = ttk.Button(add_form, text="Сохранить", command=save_data, width=25)
        save_button.grid(row=4, column=0, pady=10)

        cancel_button = ttk.Button(add_form, text="Отмена", command=add_form.destroy, width=25)
        cancel_button.grid(row=4, column=1, pady=10)

    def refactor_lake(self):

        def update_data():
            name_of_lake = lake_name_entry_refactor.get()
            if combo_box.current() == 0:
                return
            else:
                name_update = self.list_of_lakes[combo_box.current() - 1]
            if name_of_lake in ('', "Введите название озера..."):
                tk.messagebox.showerror("Ошибка", "Обязательное поле: название озера")
            else:
                try:
                    with sq.connect(self.DB_NAME) as con:
                        cur = con.cursor()

                        text_about_lake = text_field_about_lake_refactor.get(1.0, tk.END)
                        if text_about_lake.strip() == 'Введите информацию об озере...':
                            text_about_lake = 'Нет информации'
                        if self.image_lake_refactor is None or self.image_lake_refactor == 'default.png':
                            cur.execute("UPDATE lakes SET name = ?, description = ? WHERE name = ? ",
                                        (name_of_lake,
                                         text_about_lake, name_update))
                        else:
                            image_data = self.check_image(0)
                            cur.execute("UPDATE lakes SET name = ?, picture = ?, description = ? WHERE name = ? ",
                                        (name_of_lake, image_data,
                                         text_about_lake, name_update))
                except sq.OperationalError as e:
                    logging.warning(e)
                    tk.messagebox.showerror('Ошибка', 'Нет подключения к базе данных')
                    refactor_form.focus_set()
                except sq.IntegrityError as e:
                    logging.warning(e)
                    tk.messagebox.showerror('Ошибка', f'Озеро с названием {name_of_lake} уже существует в базе данных')
                    refactor_form.focus_set()
                else:
                    self.update_list_box()
                    messagebox.showinfo('Результат', 'Изменения успешно применены')
                    refactor_form.destroy()

        def selected(event):
            if combo_box.current() == 0:
                return
            box: ttk.Combobox = event.widget
            name = box.get()
            try:
                with sq.connect(self.DB_NAME) as connection:
                    cur = connection.cursor()
                    image_url, description = cur.execute("SELECT picture, description FROM lakes WHERE name = ?",
                                                         (name,)).fetchone()
            except sq.OperationalError as e:
                logging.warning(e)
                tk.messagebox.showerror('Ошибка', 'Нет подключения к базе данных')
            else:
                photo_selected = Image.open(io.BytesIO(image_url)).resize((150, 150), Image.BICUBIC)
                picture = ImageTk.PhotoImage(photo_selected)
                refactor_file_button.configure(image=picture)
                refactor_file_button.image = picture
                lake_name_entry_refactor.delete(0, tk.END)
                lake_name_entry_refactor.insert(0, name)
                lake_name_entry_refactor.configure(foreground='black')
                text_field_about_lake_refactor.delete(1.0, tk.END)
                text_field_about_lake_refactor.insert(tk.END, description)
                text_field_about_lake_refactor.configure(foreground='black')

        refactor_form = tk.Toplevel(name='refactor_window')
        self.pack_window(refactor_form)
        refactor_form.title("Ввод информации о озере")
        refactor_form.resizable(False, False)

        image = Image.open("default.png")
        image = image.resize((150, 150))
        photo = ImageTk.PhotoImage(image)

        refactor_file_button = ttk.Button(refactor_form, text="Обзор...",
                                          command=lambda: self.open_file_dialog(refactor_form, refactor_file_button),
                                          image=photo,
                                          name='image_refactor')
        refactor_file_button.image = photo
        refactor_file_button.grid(row=0, column=0, columnspan=2, padx=5, pady=5)
        delete_picture = ttk.Button(refactor_form, text="\u2715",
                                    command=lambda: self.delete_picture_of_lake(refactor_file_button),
                                    width=2)
        delete_picture.grid(row=0, column=1, padx=50, pady=10, sticky=tk.NW)

        combo_box = ttk.Combobox(refactor_form, values=['Выберите озеро'] + self.list_of_lakes, state="readonly",
                                 width=10,
                                 foreground='gray')
        combo_box.current(0)
        combo_box.grid(row=0, column=0, padx=10, pady=10, sticky=tk.NW)
        combo_box.bind("<<ComboboxSelected>>", selected)

        lake_name_entry_refactor = ttk.Entry(refactor_form, width=20)
        lake_name_entry_refactor.configure(foreground="#999")
        lake_name_entry_refactor.insert(0, "Введите название озера...")
        lake_name_entry_refactor.bind("<FocusIn>", lambda event: self.hide_text_info(event.widget, "Введите название "
                                                                                                   "озера..."))
        lake_name_entry_refactor.bind('<FocusOut>', lambda event: self.set_text_info(event.widget, "Введите название "
                                                                                                   "озера..."))
        lake_name_entry_refactor.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        delete_name = ttk.Button(refactor_form, text="\u2715",
                                 command=lambda: self.delete_name_of_lake(lake_name_entry_refactor, "Введите название "
                                                                                                    "озера..."),
                                 width=2)
        delete_name.grid(row=1, column=1, padx=5, pady=10, sticky=tk.NE)

        text_field_about_lake_refactor = tk.Text(refactor_form, width=45, height=5)
        text_field_about_lake_refactor.configure(foreground='#999')
        text_field_about_lake_refactor.insert(0.1, "Введите информацию об озере...")
        text_field_about_lake_refactor.bind("<Control-c>", lambda event: self.text_field.event_generate("<<Copy>>"))
        text_field_about_lake_refactor.bind("<FocusIn>", self.clear_entry_text)
        text_field_about_lake_refactor.bind('<FocusOut>', self.set_hint_text)
        text_field_about_lake_refactor.grid(row=2, column=0, columnspan=2, sticky=tk.S)
        delete_about_lake = ttk.Button(refactor_form, text="\u2715",
                                       command=lambda: self.delete_info_about_lake(text_field_about_lake_refactor,
                                                                                   "Введите информацию об озере..."),
                                       width=2)
        delete_about_lake.grid(row=2, column=1, padx=5, pady=10, sticky=tk.NE)

        button_about_lake = ttk.Button(refactor_form, text="Взять информацию об озере из википедии",
                                       command=lambda: connect_to_wikipedia(lake_name_entry_refactor,
                                                                            text_field_about_lake_refactor))
        button_about_lake.grid(row=3, column=0, columnspan=2, padx=5, pady=10)

        save_button = ttk.Button(refactor_form, text="Сохранить", command=update_data, width=25)
        save_button.grid(row=4, column=0, pady=10)

        cancel_button = ttk.Button(refactor_form, text="Отмена", command=refactor_form.destroy, width=25)
        cancel_button.grid(row=4, column=1, pady=10)


if __name__ == '__main__':
    App('AmDB.ini')
