"""
ARASAKA RIPPERDOC // interface (PySide6 / Qt 6).
"""
from __future__ import annotations

import sys
import threading
import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from . import core, fx
from .core import APP_NAME, VERSION
from .kit import LINE, CutFrame, Indicator, Page, SidebarBrand, button, label, load_fonts, spaced, stylesheet

EXTRA_QSS = """
QPlainTextEdit { background: #050506; border: 1px solid #2a2a31; color: #ececf0; padding: 6px; }
QPlainTextEdit#script { background: #030304; color: #c9c9cf; font-family: monospace; }
"""
STATE_COLOR = {"ok": LINE, "aviso": QColor(150, 110, 20), "erro": QColor(120, 10, 18)}
STATE_TXT = {"ok": "NOMINAL", "aviso": "ATENCAO", "erro": "CRITICO"}


class Task(QObject):
    """Roda uma leitura demorada numa thread "daemon": fechar o app no meio nao trava nem derruba nada."""
    done = Signal(object)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            r = self.fn(*self.args)
        except Exception as e:  # noqa: BLE001
            r = e
        try:
            self.done.emit(r)           # sinal entre threads: chega na thread da interface
        except RuntimeError:
            pass                        # a janela ja foi fechada


def card(title: str, state: str, text: str, actions: list[QPushButton] = ()) -> CutFrame:
    c = CutFrame(cut=12)
    c.set_border(STATE_COLOR.get(state, LINE))
    lay = QVBoxLayout(c)
    lay.setContentsMargins(18, 14, 18, 14)
    top = QHBoxLayout()
    top.addWidget(Indicator(state == "ok"))
    top.addWidget(label(title, px=2, bold=True))
    top.addStretch()
    top.addWidget(label(STATE_TXT.get(state, ""), "muted" if state == "ok" else "red", px=2, size=12))
    lay.addLayout(top)
    lay.addWidget(label(text, "muted", px=0.5, wrap=True))
    if actions:
        row = QHBoxLayout()
        row.addStretch()
        for b in actions:
            row.addWidget(b)
        lay.addLayout(row)
    return c


class ScriptDialog(QDialog):
    """Mostra exatamente o que vai rodar antes de abrir o terminal."""

    def __init__(self, parent, title: str, script: str, warn: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.addWidget(label(title.upper(), px=2, bold=True))
        if warn:
            w = label(warn, "red", wrap=True)
            lay.addWidget(w)
        lay.addWidget(label("Isto vai rodar num terminal, onde você vê tudo e digita a senha se for preciso:", "muted", wrap=True))
        ed = QPlainTextEdit(script)
        ed.setObjectName("script")
        ed.setReadOnly(True)
        ed.setMinimumHeight(180)
        lay.addWidget(ed)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("CANCELAR", None, self.reject))
        row.addWidget(button("RODAR NO TERMINAL", "danger" if "Atenção" in warn else "primary", self.accept))
        lay.addLayout(row)


class BasePage(Page):
    """Pagina que carrega os dados numa thread e redesenha os cartoes."""

    def __init__(self, win, title, subtitle, code):
        super().__init__(win, title, subtitle, code)
        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        self.lay.addLayout(self.body)
        self.lay.addStretch()
        self.task = None
        self.data = None
        self.loaded_at = 0.0

    def load(self):
        raise NotImplementedError

    def render(self, data):
        raise NotImplementedError

    def clear(self):
        while self.body.count():
            it = self.body.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                while it.layout().count():
                    w = it.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()

    def refresh(self, force=False):
        if self.task or (self.data is not None and not force and time.time() - self.loaded_at < 120):
            if self.data is not None and not self.task:
                self.clear()
                self.render(self.data)
            return
        self.clear()
        self.body.addWidget(label("■  LENDO O SISTEMA...", "muted", 2, 12, True))
        self.task = Task(self.load)
        self.task.done.connect(self._loaded)
        self.task.start()

    def _loaded(self, data):
        self.task = None
        self.clear()
        if isinstance(data, Exception):
            self.body.addWidget(card("ERRO", "erro", str(data)))
            return
        self.data, self.loaded_at = data, time.time()
        self.render(data)


# ================================================================ paginas
class DiagPage(BasePage):
    def __init__(self, win):
        super().__init__(win, "DIAGNOSTICO", "O estado geral do sistema, num lugar só", "RIPPERDOC://SCAN")

    def load(self):
        gpus = core.parse_lspci(core.sh(["lspci", "-nnk"]))
        nv = core.nvidia_info(gpus)
        return {"gpus": gpus, "nv": nv, "upd": core.updates(), "clean": core.clean_items(),
                "start": [x for x in core.autostart_items() if x.enabled]}

    def render(self, d):
        self.win.cache.update(d)
        self.body.addWidget(card("SISTEMA", "ok", f"{core.os_name()} · kernel {core.running_kernel()}"))
        nv = d["nv"]
        if nv:
            st, txt = core.nvidia_advice(nv)
            gname = next((g.name for g in d["gpus"] if g.vendor == "nvidia"), "NVIDIA")
            self.body.addWidget(card("VIDEO", st, f"{gname} · driver {nv.version or 'nouveau'}\n{txt}", [button("VER DRIVERS", None, lambda: self.win.go("drivers"))]))
        else:
            names = ", ".join(f"{g.name} ({g.driver or 'sem driver'})" for g in d["gpus"]) or "nenhuma placa encontrada"
            self.body.addWidget(card("VIDEO", "ok", f"{names}\nAMD e Intel usam os drivers abertos que já vêm no kernel."))
        u = d["upd"]
        n = len(u.apt) + len(u.flatpak) + len(u.snap) + len(u.firmware)
        stale = u.apt_age_h is not None and u.apt_age_h > 24 * 7
        self.body.addWidget(card("ATUALIZACOES", "aviso" if n or stale else "ok",
                                 (f"{n} atualização(ões) disponível(is)" if n else "Tudo em dia")
                                 + (" · a lista do apt não é atualizada há mais de uma semana" if stale else ""),
                                 [button("VER ATUALIZACOES", None, lambda: self.win.go("updates"))]))
        total = sum(c.size for c in d["clean"])
        self.body.addWidget(card("ESPACO", "aviso" if total > 2 * 1024 ** 3 else "ok",
                                 f"Dá para liberar cerca de {core.human(total)}" if total else "Nada importante para limpar",
                                 [button("VER LIMPEZA", None, lambda: self.win.go("clean"))]))
        self.body.addWidget(card("INICIALIZACAO", "ok", f"{len(d['start'])} programa(s) abrem com a sessão",
                                 [button("VER INICIALIZACAO", None, lambda: self.win.go("startup"))]))
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("ESCANEAR DE NOVO", None, lambda: self.refresh(True)))
        self.body.addLayout(row)


class DriversPage(BasePage):
    def __init__(self, win):
        super().__init__(win, "DRIVERS", "Placas de vídeo, o driver em uso e como ele foi instalado", "RIPPERDOC://CHROME")

    def load(self):
        gpus = core.parse_lspci(core.sh(["lspci", "-nnk"]))
        return {"gpus": gpus, "nv": core.nvidia_info(gpus)}

    def render(self, d):
        for g in d["gpus"]:
            vend = {"nvidia": "NVIDIA", "amd": "AMD", "intel": "INTEL"}.get(g.vendor, "VIDEO")
            if g.vendor != "nvidia":
                self.body.addWidget(card(f"{vend} · {g.slot}", "ok", f"{g.name}\nDriver: {g.driver or 'nenhum em uso (placa desativada ou sem monitor)'} · "
                                         "driver aberto do kernel, atualiza junto com o sistema."))
        nv = d["nv"]
        if not nv:
            return
        st, txt = core.nvidia_advice(nv)
        gname = next((g.name for g in d["gpus"] if g.vendor == "nvidia"), "NVIDIA")
        how = {"run": "instalador .run da NVIDIA", "pacote": f"pacote do Ubuntu ({nv.package})"}.get(nv.method, "desconhecido")
        info = (f"{gname}\nDriver {nv.version or 'não carregado'}{' (módulo aberto)' if nv.open_module else ''} · instalado por: {how}\n"
                f"Compilado para os kernels: {', '.join(nv.dkms_ok) or 'nenhum'}"
                + (f" · faltando: {', '.join(nv.dkms_missing)}" if nv.dkms_missing else "")
                + (f"\nSecure Boot {nv.secure_boot}" + (" (drivers fora dos pacotes precisam de chave assinada)" if nv.secure_boot == "ligado" else "") if nv.secure_boot else "")
                + (f"\nO Ubuntu recomenda: {nv.recommended}" if nv.recommended else "")
                + f"\n\n{txt}")
        acts = []
        for key, (title, script, warn) in core.nvidia_scripts(nv).items():
            acts.append(button(title.upper(), "primary" if key == "dkms" else None, lambda t=title, s=script, w=warn: self.win.run_script(t, s, w, self)))
        self.body.addWidget(card(f"NVIDIA · {nv.version or '—'}", st, info, acts))


class UpdatesPage(BasePage):
    def __init__(self, win):
        super().__init__(win, "ATUALIZACOES", "Pacotes do sistema, Flatpak, Snap e firmware", "RIPPERDOC://PATCH")

    def load(self):
        return core.updates()

    def render(self, u):
        def lst(xs):
            return ", ".join(xs[:12]) + (f" e mais {len(xs) - 12}" if len(xs) > 12 else "")
        age = f" · lista do apt de {u.apt_age_h:.0f} h atrás" if u.apt_age_h is not None else ""
        self.body.addWidget(card("SISTEMA (APT)", "aviso" if u.apt else "ok", (f"{len(u.apt)} pacote(s): {lst(u.apt)}" if u.apt else "Em dia") + age))
        if core.shutil.which("flatpak"):
            self.body.addWidget(card("FLATPAK", "aviso" if u.flatpak else "ok", f"{len(u.flatpak)}: {lst(u.flatpak)}" if u.flatpak else "Em dia"))
        if core.shutil.which("snap"):
            self.body.addWidget(card("SNAP", "aviso" if u.snap else "ok", f"{len(u.snap)}: {lst(u.snap)}" if u.snap else "Em dia"))
        if core.shutil.which("fwupdmgr"):
            self.body.addWidget(card("FIRMWARE", "aviso" if u.firmware else "ok", f"Novo firmware para: {lst(u.firmware)}" if u.firmware else "Em dia (BIOS, SSD, periféricos compatíveis)"))
        row = QHBoxLayout()
        row.addWidget(button("ATUALIZAR TUDO", "primary", lambda: self.win.run_script("Atualizar tudo", core.update_script(u), "", self)))
        row.addWidget(button("VERIFICAR DE NOVO", None, lambda: self.refresh(True)))
        row.addStretch()
        self.body.addLayout(row)
        self.body.addWidget(label("A lista do apt é renovada ao atualizar (precisa da senha). Antes disso, mostra o que o sistema já sabe.", "dim", wrap=True))


class CleanPage(BasePage):
    def __init__(self, win):
        super().__init__(win, "LIMPEZA", "Espaço que dá para liberar com segurança", "RIPPERDOC://PURGE")
        self.checks: dict[str, QCheckBox] = {}

    def load(self):
        return core.clean_items()

    def render(self, items):
        self.checks = {}
        if not items:
            self.body.addWidget(card("LIMPO", "ok", "Nada importante para limpar."))
            return
        for it in items:
            c = CutFrame(cut=10)
            lay = QHBoxLayout(c)
            lay.setContentsMargins(16, 10, 16, 10)
            cb = QCheckBox()
            cb.setChecked(it.key not in ("trash", "usercache"))
            self.checks[it.key] = cb
            lay.addWidget(cb)
            col = QVBoxLayout()
            col.addWidget(label(it.title.upper(), px=2, bold=True))
            col.addWidget(label(it.detail, "muted", wrap=True))
            lay.addLayout(col, 1)
            lay.addWidget(label(core.human(it.size) if it.size else "—", px=1.5, bold=True))
            self.body.addWidget(c)
        row = QHBoxLayout()
        row.addWidget(button("LIMPAR O QUE ESTA MARCADO", "primary", lambda: self.run(items)))
        row.addWidget(button("VERIFICAR DE NOVO", None, lambda: self.refresh(True)))
        row.addStretch()
        self.body.addLayout(row)

    def run(self, items):
        pick = [i for i in items if self.checks.get(i.key) and self.checks[i.key].isChecked()]
        if not pick:
            return self.win.toast("Marque o que quer limpar")
        script = "\n".join(f'echo "■ {i.title}"\n{i.script}' for i in pick)
        warn = "Esvaziar a lixeira e apagar o cache não dá para desfazer." if any(i.key in ("trash", "usercache") for i in pick) else ""
        self.win.run_script("Limpeza", script, warn, self)


class StartupPage(BasePage):
    def __init__(self, win):
        super().__init__(win, "INICIALIZACAO", "O que abre sozinho quando você entra na sessão", "RIPPERDOC://BOOT")

    def load(self):
        return {"auto": core.autostart_items(), "svc": core.user_services()}

    def render(self, d):
        self.body.addWidget(label("PROGRAMAS DA SESSAO", "muted", 2, 12, True))
        for it in d["auto"]:
            cb = QCheckBox(f"{it.title}   ·   {it.detail[:90]}" + ("   ·   do sistema" if it.system else ""))
            cb.setChecked(it.enabled)
            cb.toggled.connect(lambda on, x=it: self.toggle_auto(x, on))
            self.body.addWidget(cb)
        if d["svc"]:
            self.body.addSpacing(8)
            self.body.addWidget(label("SERVICOS DO SEU USUARIO", "muted", 2, 12, True))
            for it in d["svc"]:
                cb = QCheckBox(f"{it.title}   ·   {it.detail[:90]}")
                cb.setChecked(it.enabled)
                cb.toggled.connect(lambda on, x=it, box=cb: self.toggle_svc(x, on, box))
                self.body.addWidget(cb)
        self.body.addWidget(label("Desligar só impede de abrir sozinho: o programa continua instalado. Mudanças valem no próximo login.", "dim", wrap=True))

    def toggle_auto(self, it, on):
        try:
            core.set_autostart(it, on)
            self.win.toast(f"{it.title}: {'liga' if on else 'não abre mais'} ao entrar")
        except Exception as e:  # noqa: BLE001
            self.win.alert("Inicialização", str(e))

    def toggle_svc(self, it, on, box):
        err = core.set_user_service(it, on)
        if err:
            box.blockSignals(True)
            box.setChecked(not on)
            box.blockSignals(False)
            self.win.alert("Serviço", err)
        else:
            self.win.toast(f"{it.title}: {'ligado' if on else 'desligado'}")


# ================================================================ janela
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 800)
        self.cache = {}
        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 14)
        sl.setSpacing(2)
        sl.addWidget(SidebarBrand("RIPPERDOC"))
        sl.addSpacing(10)
        self.nav = QButtonGroup(self)
        self.stack = QStackedWidget()
        self.pages = {"diag": DiagPage(self), "drivers": DriversPage(self), "updates": UpdatesPage(self),
                      "clean": CleanPage(self), "startup": StartupPage(self)}
        for i, (key, text) in enumerate([("diag", "DIAGNOSTICO"), ("drivers", "DRIVERS"), ("updates", "ATUALIZACOES"),
                                         ("clean", "LIMPEZA"), ("startup", "INICIALIZACAO")]):
            b = QPushButton(f"{i + 1:02d}   {text}")
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            spaced(b, 2.5)
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            self.nav.addButton(b, i)
            sl.addWidget(b)
            self.stack.addWidget(self.pages[key])
        sl.addStretch()
        k = label(f"KERNEL {core.running_kernel()}", "dim", 1.5, 11, True)
        k.setContentsMargins(20, 0, 0, 0)
        sl.addWidget(k)
        ver = label(f"RIPPERDOC v{VERSION}", "dim", 2, 11)
        ver.setContentsMargins(20, 0, 0, 0)
        sl.addWidget(ver)
        h.addWidget(side)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.toast_lbl = QLabel(self)
        self.toast_lbl.setStyleSheet("background:#000; border:1px solid #e3121f; padding:10px 18px; color:#ececf0;")
        self.toast_lbl.hide()
        self.status_file = core.HOME / ".cache" / core.APP_ID / "ultimo"
        self.watch = QTimer(self)
        self.watch.timeout.connect(self._check_terminal)
        self.watch_page = None
        self.go("diag")

    def go(self, key: str):
        self.nav.button(list(self.pages).index(key)).setChecked(True)
        self.stack.setCurrentWidget(self.pages[key])
        self.pages[key].refresh()

    def run_script(self, title: str, script: str, warn: str, page):
        if self.watch.isActive():
            return self.toast("Espere o terminal aberto terminar")
        if ScriptDialog(self, title, script, warn).exec() != QDialog.Accepted:
            return
        err = core.open_terminal(script, title, self.status_file)
        if err:
            return self.alert(title, err)
        self.watch_page = page
        self.watch.start(1000)
        self.toast("Siga no terminal que abriu")

    def _check_terminal(self):
        if not self.status_file.exists():
            return
        self.watch.stop()
        code = self.status_file.read_text().strip()
        self.toast("Concluído" if code == "0" else f"Terminou com erro (código {code})")
        for p in self.pages.values():
            p.data = None
        if self.watch_page:
            self.watch_page.refresh(True)

    def toast(self, text: str):
        self.toast_lbl.setText(text)
        spaced(self.toast_lbl, 1)
        self.toast_lbl.adjustSize()
        self.toast_lbl.move(self.width() - self.toast_lbl.width() - 24, 20)
        self.toast_lbl.raise_()
        self.toast_lbl.show()
        QTimer.singleShot(3500, self.toast_lbl.hide)

    def alert(self, title: str, text: str):
        mb = QMessageBox(self)
        mb.setWindowTitle(title)
        mb.setText(text)
        mb.addButton("OK", QMessageBox.AcceptRole).setProperty("kind", "primary")
        mb.exec()


def main(argv: list[str] | None = None):
    argv = list(sys.argv if argv is None else argv)
    QApplication.setApplicationName(core.APP_ID)
    QApplication.setApplicationDisplayName(APP_NAME)
    QApplication.setDesktopFileName(core.APP_ID)
    app = QApplication(argv)
    load_fonts()
    app.setStyleSheet(stylesheet() + EXTRA_QSS)
    app.setWindowIcon(QIcon(str(core.ASSETS / "arasaka-ripperdoc.svg")))
    win = MainWindow()
    fx.install(win, name=APP_NAME, icon=core.ASSETS / "arasaka-ripperdoc.svg", boot=not any(a.startswith("--screenshot=") for a in argv))
    win.show()
    shot = next((a.split("=", 1)[1] for a in argv if a.startswith("--screenshot=")), None)
    if shot:
        path, _, page = shot.partition(",")
        if page:
            QTimer.singleShot(200, lambda: win.go(page))
        QTimer.singleShot(int(next((a.split("=", 1)[1] for a in argv if a.startswith("--delay=")), "2600")), lambda: (win.grab().save(path), app.quit()))
    return app.exec()
