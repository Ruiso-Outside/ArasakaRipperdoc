"""
ARASAKA RIPPERDOC // nucleo: diagnostico do Linux (drivers, kernels, atualizacoes, limpeza, inicializacao).

So le o sistema. Tudo que muda algo vira um script mostrado antes e rodado num terminal (para a pessoa ver
e digitar a senha do sudo). Os "parse_*" recebem o texto dos comandos, para dar para testar sem o sistema.
"""
from __future__ import annotations

import configparser
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

APP_ID = "arasaka-ripperdoc"
APP_NAME = "ARASAKA RIPPERDOC"
VERSION = "1.0.0"

HOME = Path.home()
ASSETS = Path(__file__).resolve().parent / "assets"
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))


def sh(args: list[str], timeout: float = 60) -> str:
    """Roda um comando de leitura e devolve a saida (vazio se nao existir ou falhar)."""
    if not shutil.which(args[0]):
        return ""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env={**os.environ, "LC_ALL": "C"})
        return r.stdout
    except Exception:
        return ""


def human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def dir_size(p: Path) -> int:
    total = 0
    for root, _d, files in os.walk(p, onerror=lambda e: None):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


# ================================================================ sistema
def os_name() -> str:
    for f in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            m = re.search(r'^PRETTY_NAME="?([^"\n]+)', Path(f).read_text(), re.M)
            if m:
                return m.group(1)
        except OSError:
            pass
    return "Linux"


def running_kernel() -> str:
    return os.uname().release


# ================================================================ placas de video e drivers
@dataclass
class Gpu:
    slot: str
    vendor: str          # nvidia | amd | intel | outro
    name: str
    driver: str          # modulo em uso (nvidia, amdgpu, i915, nouveau...) ou ""
    pci_id: str = ""


def parse_lspci(text: str) -> list[Gpu]:
    gpus, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^(\S+) (VGA compatible controller|3D controller|Display controller) \[[0-9a-f]+\]: (.+?)(?: \(rev \w+\))?$", line)
        if m:
            desc = m.group(3)
            ids = re.search(r"\[([0-9a-f]{4}):([0-9a-f]{4})\]\s*$", desc)
            vendor = {"10de": "nvidia", "1002": "amd", "8086": "intel"}.get(ids.group(1) if ids else "", "outro")
            name = re.sub(r"\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]\s*$", "", desc)
            cur = Gpu(m.group(1), vendor, name, "", ids.group(0).strip("[]") if ids else "")
            gpus.append(cur)
        elif line and not line[0].isspace():
            cur = None
        elif cur is not None:
            d = re.match(r"\s+Kernel driver in use: (\S+)", line)
            if d:
                cur.driver = d.group(1)
    return gpus


@dataclass
class NvidiaInfo:
    version: str = ""        # versao carregada (ex.: 620.73.04)
    open_module: bool = False
    method: str = ""         # run | pacote | ""
    package: str = ""        # nvidia-driver-595-open, se for pacote
    dkms_ok: list[str] = field(default_factory=list)       # kernels com o modulo compilado
    dkms_missing: list[str] = field(default_factory=list)  # kernels instalados sem o modulo
    recommended: str = ""    # pacote recomendado pelo ubuntu-drivers
    offered: list[str] = field(default_factory=list)       # pacotes oferecidos
    secure_boot: str = ""    # "ligado" | "desligado" | ""


def parse_nvidia_proc(text: str) -> tuple[str, bool]:
    m = re.search(r"Kernel Module(?: for \S+)?\s+([\d.]+)", text)
    return (m.group(1) if m else ""), ("Open Kernel Module" in text)


def parse_dkms(text: str, module: str = "nvidia") -> dict[str, str]:
    """{kernel: estado} do modulo no `dkms status` (formatos antigo e novo)."""
    out = {}
    for line in text.splitlines():
        m = re.match(rf"^{module}[/,]\s*([\d.]+),\s*([^,]+),\s*[^:]+:\s*(\w+)", line)
        if m:
            out[m.group(2).strip()] = m.group(3)
    return out


def parse_ubuntu_drivers(text: str) -> tuple[str, list[str]]:
    rec, offered = "", []
    for line in text.splitlines():
        m = re.match(r"^driver\s*:\s*(nvidia-driver-\S+)\s+-\s+.*?(recommended)?\s*$", line)
        if m:
            offered.append(m.group(1))
            if m.group(2):
                rec = m.group(1)
    return rec, offered


def driver_major(pkg_or_version: str) -> int:
    m = re.search(r"(\d{3})", pkg_or_version or "")
    return int(m.group(1)) if m else 0


def installed_kernels(dpkg_text: str) -> list[str]:
    ks = []
    for line in dpkg_text.splitlines():
        m = re.match(r"^ii\s+linux-image-(\d[\w.\-]+?)\s", line)
        if m and not m.group(1).startswith("unsigned"):
            ks.append(m.group(1))
    return sorted(set(ks), key=_kver)


def _kver(k: str):
    return [int(x) if x.isdigit() else x for x in re.split(r"[.\-]", k)]


def nvidia_info(gpus: list[Gpu]) -> NvidiaInfo | None:
    if not any(g.vendor == "nvidia" for g in gpus):
        return None
    names = [l.strip() for l in sh(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]).splitlines() if l.strip()]
    for g, nm in zip([g for g in gpus if g.vendor == "nvidia"], names):
        g.name = nm                      # o banco do lspci costuma nao conhecer as placas novas
    n = NvidiaInfo()
    try:
        n.version, n.open_module = parse_nvidia_proc(Path("/proc/driver/nvidia/version").read_text())
    except OSError:
        pass
    pk = [l.split()[1] for l in sh(["dpkg", "-l", "nvidia-driver-*"]).splitlines() if l.startswith("ii")]
    if pk:
        n.method, n.package = "pacote", pk[0]
    elif Path("/usr/bin/nvidia-uninstall").exists():
        n.method = "run"
    kernels = installed_kernels(sh(["dpkg", "-l", "linux-image-*"]))
    st = parse_dkms(sh(["dkms", "status"]))
    n.dkms_ok = [k for k in kernels if st.get(k) == "installed"]
    n.dkms_missing = [k for k in kernels if st.get(k) != "installed"] if st else []
    n.recommended, n.offered = parse_ubuntu_drivers(sh(["ubuntu-drivers", "devices"], timeout=90))
    sb = sh(["mokutil", "--sb-state"])
    n.secure_boot = "ligado" if "enabled" in sb else "desligado" if "disabled" in sb else ""
    return n


def nvidia_advice(n: NvidiaInfo) -> tuple[str, str]:
    """(estado: ok|aviso|erro, texto explicando)"""
    if not n.version:
        if n.method:
            return "erro", "O driver da NVIDIA está instalado, mas não está carregado (talvez falte reiniciar ou recompilar para o kernel atual)."
        return "aviso", "Usando o driver aberto nouveau (sem aceleração 3D boa para jogos). Instale um driver da NVIDIA."
    if n.dkms_missing:
        newer = [k for k in n.dkms_missing if _kver(k) > _kver(running_kernel())]
        if newer:
            return "erro", (f"O driver não está compilado para o kernel {', '.join(newer)}, que é o que o PC vai usar no próximo "
                            "início: a tela pode ficar sem vídeo da NVIDIA. Recompile antes de reiniciar.")
        return "aviso", (f"O driver não está compilado para o kernel antigo {', '.join(n.dkms_missing)} (reserva do menu do GRUB): "
                         "se iniciar por ele, fica sem vídeo da NVIDIA. Recompile ou remova esse kernel.")
    if n.method == "run":
        newer = n.recommended and driver_major(n.recommended) > driver_major(n.version)
        if newer:
            return "aviso", f"Instalado pelo .run da NVIDIA. O Ubuntu já oferece um mais novo ({n.recommended}), que atualiza junto com o sistema."
        return "ok", ("Instalado pelo .run da NVIDIA, com DKMS: é recompilado sozinho quando o kernel atualiza. "
                      f"O Ubuntu oferece {n.recommended or 'versões'} (mais antigo que o seu); manter o .run está ok.")
    if n.method == "pacote":
        if n.recommended and driver_major(n.recommended) > driver_major(n.package):
            return "aviso", f"Há um driver mais novo nos pacotes: {n.recommended}."
        return "ok", "Driver dos pacotes do Ubuntu: atualiza junto com o sistema."
    return "ok", "Driver carregado."


# ================================================================ atualizacoes
@dataclass
class Updates:
    apt: list[str] = field(default_factory=list)
    flatpak: list[str] = field(default_factory=list)
    snap: list[str] = field(default_factory=list)
    firmware: list[str] = field(default_factory=list)
    apt_age_h: float | None = None     # horas desde o ultimo apt update


def parse_apt_upgradable(text: str) -> list[str]:
    return [l.split("/")[0] for l in text.splitlines() if "/" in l and "[upgradable" in l]


def parse_flatpak_updates(text: str) -> list[str]:
    return [l.split("\t")[0].strip() for l in text.splitlines() if l.strip() and not l.startswith("Name")]


def parse_snap_refresh(text: str) -> list[str]:
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines or "All snaps up to date" in text:
        return []
    return [l.split()[0] for l in lines[1:] if l.split()]


def parse_fwupd(text: str) -> list[str]:
    """Nomes dos aparelhos com firmware novo (arvore do fwupdmgr get-updates)."""
    names = [m.strip() for m in re.findall(r"^[│├└─\s]*[├└]─(.+?):\s*$", text, re.M)]
    return sorted(set(names)) or (["firmware"] if re.search(r"New version|Nova vers", text) else [])


def updates() -> Updates:
    u = Updates()
    u.apt = parse_apt_upgradable(sh(["apt", "list", "--upgradable"]))
    try:
        import time
        u.apt_age_h = (time.time() - os.stat("/var/lib/apt/periodic/update-success-stamp").st_mtime) / 3600
    except OSError:
        try:
            import time
            u.apt_age_h = (time.time() - os.stat("/var/cache/apt/pkgcache.bin").st_mtime) / 3600
        except OSError:
            pass
    u.flatpak = parse_flatpak_updates(sh(["flatpak", "remote-ls", "--updates", "--columns=name"], timeout=90))
    u.snap = parse_snap_refresh(sh(["snap", "refresh", "--list"], timeout=60))
    fw = sh(["fwupdmgr", "get-updates", "--no-unreported-check", "--no-metadata-check"], timeout=60)
    u.firmware = [] if not fw or re.search(r"No updat|No upgrades|no updates", fw) else parse_fwupd(fw)
    return u


def update_script(u: Updates) -> str:
    lines = ["set -e", 'echo "■ Atualizando os pacotes do sistema (apt)"', "sudo apt-get update",
             "sudo DEBIAN_FRONTEND=noninteractive apt-get full-upgrade -y"]
    if shutil.which("flatpak"):
        lines += ['echo "■ Atualizando os Flatpaks"', "flatpak update -y --noninteractive || true"]
    if shutil.which("snap"):
        lines += ['echo "■ Atualizando os Snaps"', "sudo snap refresh || true"]
    if u.firmware and shutil.which("fwupdmgr"):
        lines += ['echo "■ Atualizando o firmware (pode pedir para reiniciar)"', "fwupdmgr update -y --no-reboot-check || true"]
    lines += ['[ -f /var/run/reboot-required ] && echo "!! Reinicie o PC para terminar a atualização" || true']
    return "\n".join(lines)


# ================================================================ limpeza
@dataclass
class CleanItem:
    key: str
    title: str
    detail: str
    size: int
    script: str           # o que roda (num terminal, mostrado antes)
    needs_root: bool = True


def old_kernels(installed: list[str], running: str, keep: int = 1) -> list[str]:
    """Kernels que podem sair: todos menos o atual e os `keep` mais novos alem dele."""
    others = [k for k in installed if k != running]
    newest = sorted(others, key=_kver)[-keep:] if keep else []
    return [k for k in others if k not in newest and _kver(k) < _kver(running)]


def parse_autoremove(text: str) -> list[str]:
    return re.findall(r"^Remv (\S+)", text, re.M)


def clean_items() -> list[CleanItem]:
    items = []
    kernels = installed_kernels(sh(["dpkg", "-l", "linux-image-*"]))
    old = old_kernels(kernels, running_kernel())
    if old:
        pkgs = " ".join(f"linux-image-{k} linux-headers-{k} linux-modules-{k} linux-modules-extra-{k}" for k in old)
        size = sum(dir_size(Path(f"/lib/modules/{k}")) + sum(p.stat().st_size for p in Path("/boot").glob(f"*{k}*") if p.is_file()) for k in old)
        items.append(CleanItem("kernels", "Kernels antigos", f"{', '.join(old)} (fica o atual, {running_kernel()}, e o anterior a ele)", size,
                               f"sudo apt-get purge -y $(dpkg-query -W -f='${{Package}} ' {pkgs} 2>/dev/null)\nsudo update-grub"))
    auto = parse_autoremove(sh(["apt-get", "-s", "autoremove"]))
    if auto:
        items.append(CleanItem("autoremove", "Pacotes que ninguém usa", f"{len(auto)} pacote(s) instalados como dependência e que sobraram", 0,
                               "sudo apt-get autoremove -y"))
    cache = sum(p.stat().st_size for p in Path("/var/cache/apt/archives").glob("*.deb")) if Path("/var/cache/apt/archives").is_dir() else 0
    if cache > 20 * 1024 * 1024:
        items.append(CleanItem("aptcache", "Instaladores baixados (apt)", "os .deb já instalados guardados em /var/cache/apt", cache, "sudo apt-get clean"))
    if shutil.which("flatpak"):
        items.append(CleanItem("flatpak", "Flatpaks sem uso", "runtimes que nenhum app usa mais", 0,
                               "flatpak uninstall --unused -y --noninteractive", needs_root=False))
    j = re.search(r"take up ([\d.]+)([KMGT])", sh(["journalctl", "--disk-usage"]))
    if j:
        size = int(float(j.group(1)) * 1024 ** "KMGT".index(j.group(2)) * 1024)
        if size > 200 * 1024 * 1024:
            items.append(CleanItem("journal", "Registros do sistema antigos", "mantém só as últimas 2 semanas", size,
                                   "sudo journalctl --vacuum-time=2weeks"))
    cache_dir = HOME / ".cache"
    if cache_dir.is_dir():
        size = dir_size(cache_dir)
        if size > 100 * 1024 * 1024:
            items.append(CleanItem("usercache", "Cache dos seus apps", "~/.cache (os apps recriam o que precisarem; feche-os antes)", size,
                                   "find ~/.cache -mindepth 1 -maxdepth 1 -exec rm -rf {} +", needs_root=False))
    trash = HOME / ".local/share/Trash"
    if trash.is_dir():
        size = dir_size(trash)
        if size > 0:
            items.append(CleanItem("trash", "Lixeira", "esvazia a lixeira (não dá para desfazer)", size, "gio trash --empty", needs_root=False))
    return items


# ================================================================ inicializacao
@dataclass
class StartupItem:
    key: str              # nome do .desktop ou da unidade
    title: str
    detail: str
    enabled: bool
    kind: str             # autostart | servico
    system: bool = False  # do sistema (o override fica na pasta do usuario)


def autostart_items() -> list[StartupItem]:
    dirs = [Path("/etc/xdg/autostart"), CONFIG_HOME / "autostart"]
    found: dict[str, StartupItem] = {}
    for d in dirs:
        for f in sorted(d.glob("*.desktop")) if d.is_dir() else []:
            cp = configparser.RawConfigParser(interpolation=None, strict=False)
            cp.optionxform = str
            try:
                cp.read(f, encoding="utf-8")
                e = cp["Desktop Entry"]
            except Exception:
                continue
            desk = os.environ.get("XDG_CURRENT_DESKTOP", "GNOME").split(":")
            if e.get("OnlyShowIn") and not set(e["OnlyShowIn"].strip(";").split(";")) & set(desk):
                found.pop(f.name, None)
                continue
            enabled = e.get("Hidden") != "true" and e.get("X-GNOME-Autostart-enabled", "true") != "false"
            system = d == dirs[0] and f.name not in found
            title = e.get(f"Name[{os.environ.get('LANG', 'pt_BR').split('.')[0]}]") or e.get("Name") or f.stem
            prev = found.get(f.name)
            found[f.name] = StartupItem(f.name, title, e.get("Comment", "") or e.get("Exec", ""), enabled, "autostart",
                                        system=prev.system if prev else system)
    return sorted(found.values(), key=lambda x: x.title.lower())


def set_autostart(item: StartupItem, on: bool):
    """Liga/desliga pela copia na pasta do usuario (nao mexe em /etc)."""
    user = CONFIG_HOME / "autostart" / item.key
    src = user if user.exists() else Path("/etc/xdg/autostart") / item.key
    text = src.read_text(encoding="utf-8")
    text = re.sub(r"^(Hidden|X-GNOME-Autostart-enabled)=.*\n?", "", text, flags=re.M)
    if not on:
        text = text.replace("[Desktop Entry]\n", "[Desktop Entry]\nX-GNOME-Autostart-enabled=false\n", 1)
    user.parent.mkdir(parents=True, exist_ok=True)
    user.write_text(text, encoding="utf-8")


def parse_unit_files(text: str) -> list[tuple[str, str]]:
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith((".service", ".timer")) and parts[1] in ("enabled", "disabled"):
            out.append((parts[0], parts[1]))
    return out


def user_services() -> list[StartupItem]:
    out = []
    for unit, state in parse_unit_files(sh(["systemctl", "--user", "list-unit-files", "--type=service,timer", "--no-legend", "--no-pager"])):
        if "@" in unit:
            continue
        desc = sh(["systemctl", "--user", "show", unit, "-p", "Description", "--value"]).strip()
        out.append(StartupItem(unit, unit.rsplit(".", 1)[0], desc, state == "enabled", "servico"))
    return out


def set_user_service(item: StartupItem, on: bool) -> str:
    r = subprocess.run(["systemctl", "--user", "enable" if on else "disable", "--now", item.key], capture_output=True, text=True)
    return "" if r.returncode == 0 else (r.stderr.strip()[:200] or "falhou")


# ================================================================ scripts de driver
def nvidia_scripts(n: NvidiaInfo) -> dict[str, tuple[str, str, str]]:
    """{acao: (titulo, script, aviso)} conforme o estado do driver."""
    out = {}
    if n.dkms_missing:
        out["dkms"] = ("Recompilar para todos os kernels",
                       "\n".join(f"sudo apt-get install -y linux-headers-{shlex.quote(k)} || true\nsudo dkms install nvidia/{n.version} -k {shlex.quote(k)}"
                                 for k in n.dkms_missing) + "\necho; dkms status",
                       "Compila o driver atual para os kernels que estão sem ele. Leva alguns minutos.")
    if n.recommended:
        steps = []
        if n.method == "run":
            steps += ['echo "■ Removendo o driver instalado pelo .run"', "sudo nvidia-uninstall --silent || sudo nvidia-installer --uninstall --silent"]
        steps += [f'echo "■ Instalando {n.recommended} (pacote do Ubuntu)"', "sudo apt-get update",
                  f"sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {shlex.quote(n.recommended)}",
                  'echo; echo "!! Reinicie o PC para usar o driver novo"']
        title = "Trocar pelo pacote do Ubuntu" if n.method == "run" else f"Instalar {n.recommended}"
        older = n.version and driver_major(n.recommended) < driver_major(n.version)
        warn = (f"Instala o {n.recommended}. "
                + (f"Atenção: ele é MAIS ANTIGO que o seu driver atual ({n.version}). Só troque se o atual estiver dando problema. " if older else "")
                + "Troca o driver de vídeo: feche os jogos e salve o que estiver aberto. Depois é preciso reiniciar; se a tela ficar preta, "
                "no menu do GRUB escolha \"Advanced options\" e o modo de recuperação.")
        if n.method != "pacote" or n.package != n.recommended:
            out["package"] = (title, "set -e\n" + "\n".join(steps), warn)
    return out


# ================================================================ terminal
TERMINALS = [("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--"]), ("ptyxis", ["--"]), ("kgx", ["--"]),
             ("konsole", ["-e"]), ("xfce4-terminal", ["-x"]), ("tilix", ["-e"]), ("xterm", ["-e"])]


def open_terminal(script: str, title: str, status_file: Path) -> str | None:
    """Roda o script num terminal visivel. Ao terminar, grava o codigo de saida em status_file."""
    term = next(((shutil.which(b), a) for b, a in TERMINALS if shutil.which(b)), None)
    if not term:
        return "nenhum terminal encontrado"
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.unlink(missing_ok=True)
    wrapper = status_file.with_suffix(".sh")
    q = shlex.quote
    wrapper.write_text("\n".join([
        "#!/usr/bin/env bash",
        f"printf '\\033]0;%s\\007' {q(title)}",
        'printf "\\033[38;2;227;18;31m■ ARASAKA RIPPERDOC\\033[0m  %s\\n\\n" ' + q(title),
        "bash <<'RIPPERDOC_SCRIPT'",
        script,
        "RIPPERDOC_SCRIPT",
        "code=$?",
        f'echo "$code" > {q(str(status_file))}',
        "echo",
        'if [ "$code" -eq 0 ]; then echo "■ Pronto. Pode fechar esta janela."; else echo "!! Terminou com erro (código $code)."; fi',
        'read -r -p "Aperte Enter para fechar " _',
        "",
    ]), encoding="utf-8")
    wrapper.chmod(0o755)
    subprocess.Popen([term[0], *term[1], "bash", str(wrapper)], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return None
