"""Leitura das saidas dos comandos (lspci, dkms, ubuntu-drivers, apt...) e as decisoes do Ripperdoc.

    python tests/test_parsers.py
"""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arasaka_ripperdoc import core as C  # noqa: E402

LSPCI = """01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2c05] (rev a1)
\tSubsystem: Gigabyte Technology Co., Ltd Device [1458:4183]
\tKernel driver in use: nvidia
\tKernel modules: nvidiafb, nouveau, nvidia_drm, nvidia
7a:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Device [1002:13c0] (rev c9)
\tKernel modules: amdgpu
00:02.0 VGA compatible controller [0300]: Intel Corporation Alder Lake-P GT2 [Iris Xe Graphics] [8086:46a6] (rev 0c)
\tKernel driver in use: i915
"""
g = C.parse_lspci(LSPCI)
assert [x.vendor for x in g] == ["nvidia", "amd", "intel"]
assert g[0].driver == "nvidia" and g[1].driver == "" and g[2].driver == "i915"
assert g[2].name == "Intel Corporation Alder Lake-P GT2 [Iris Xe Graphics]"

v, open_mod = C.parse_nvidia_proc("NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  620.73.04  Release Build  (dvs-builder@U22)")
assert v == "620.73.04" and open_mod
v, open_mod = C.parse_nvidia_proc("NVRM version: NVIDIA UNIX x86_64 Kernel Module  550.120  Fri Sep 13 10:10:01 UTC 2024")
assert v == "550.120" and not open_mod

assert C.parse_dkms("nvidia/620.73.04, 7.0.0-43-generic, x86_64: installed\nvirtualbox/7.0, 7.0.0-43-generic, x86_64: installed") == {"7.0.0-43-generic": "installed"}
assert C.parse_dkms("nvidia, 550.120, 6.8.0-45-generic, x86_64: installed") == {"6.8.0-45-generic": "installed"}

rec, offered = C.parse_ubuntu_drivers("""vendor   : NVIDIA Corporation
driver   : nvidia-driver-615-open - distro non-free
driver   : nvidia-driver-595-open - distro non-free recommended
driver   : xserver-xorg-video-nouveau - distro free builtin""")
assert rec == "nvidia-driver-595-open" and offered == ["nvidia-driver-615-open", "nvidia-driver-595-open"]

ks = C.installed_kernels("ii  linux-image-6.14.0-37-generic 6.14.0-37.37 amd64 x\nii  linux-image-7.0.0-43-generic 7.0 amd64 x\nrc  linux-image-6.8.0-1-generic 6.8 amd64 x")
assert ks == ["6.14.0-37-generic", "7.0.0-43-generic"]
assert C.old_kernels(ks, "7.0.0-43-generic") == [], "fica o atual e o anterior"
assert C.old_kernels(["6.8.0-40-generic", "6.11.0-1-generic", "6.14.0-37-generic", "7.0.0-43-generic"], "7.0.0-43-generic") == ["6.8.0-40-generic", "6.11.0-1-generic"]
assert C.old_kernels(["6.14.0-37-generic", "7.0.0-43-generic"], "6.14.0-37-generic") == [], "nunca tira o kernel mais novo"

assert C.parse_apt_upgradable("Listing...\nfirefox/noble-updates 133.0 amd64 [upgradable from: 132.0]\nlibc6/noble 2.39 amd64 [upgradable from: 2.38]") == ["firefox", "libc6"]
assert C.parse_autoremove("NOTE: simulation\nRemv libfoo1 [1.0]\nRemv libbar2 [2.0]\n") == ["libfoo1", "libbar2"]
assert C.parse_snap_refresh("All snaps up to date.") == []
assert C.parse_snap_refresh("Name  Version  Rev  Publisher\nfirefox  133  5000  mozilla\n") == ["firefox"]
assert C.parse_unit_files("pipewire.service enabled enabled\ngamemoded.service disabled enabled\nfoo@.service disabled enabled") == \
    [("pipewire.service", "enabled"), ("gamemoded.service", "disabled"), ("foo@.service", "disabled")]

# decisoes sobre o driver da NVIDIA
with mock.patch.object(C, "running_kernel", return_value="7.0.0-43-generic"):
    n = C.NvidiaInfo(version="620.73.04", method="run", dkms_ok=["7.0.0-43-generic"], recommended="nvidia-driver-595-open")
    st, txt = C.nvidia_advice(n)
    assert st == "ok" and "mais antigo" in txt
    n.dkms_missing = ["6.14.0-37-generic"]
    assert C.nvidia_advice(n)[0] == "aviso", "kernel antigo sem o driver: so aviso"
    n.dkms_missing = ["7.1.0-1-generic"]
    assert C.nvidia_advice(n)[0] == "erro", "kernel novo sem o driver: critico"
    sc = C.nvidia_scripts(n)
    assert "dkms install nvidia/620.73.04 -k 7.1.0-1-generic" in sc["dkms"][1]
    assert "MAIS ANTIGO" in sc["package"][2], "avisa quando o pacote e mais antigo que o .run"
    n2 = C.NvidiaInfo(version="550.120", method="pacote", package="nvidia-driver-550", recommended="nvidia-driver-595-open")
    assert C.nvidia_advice(n2)[0] == "aviso" and "MAIS ANTIGO" not in C.nvidia_scripts(n2)["package"][2]
    assert C.nvidia_advice(C.NvidiaInfo())[0] == "aviso", "sem driver NVIDIA (nouveau)"

assert "full-upgrade" in C.update_script(C.Updates())
print("OK: lspci, driver da NVIDIA, dkms, ubuntu-drivers, kernels, apt, snap, serviços e decisões")
