# ARASAKA RIPPERDOC

Manutenção do Linux com o visual da Arasaka, para **Zorin OS e Ubuntu**: driver de vídeo, atualizações,
limpeza e o que abre sozinho na sessão, numa tela só.

O Ripperdoc **só lê** o sistema. Tudo que muda alguma coisa vira um script que aparece antes, por inteiro,
e roda num terminal, onde você vê o que acontece e digita a senha quando for preciso.

## Abas

| Aba | O que tem |
|---|---|
| **01 Diagnóstico** | Resumo: sistema e kernel, vídeo, atualizações pendentes, espaço que dá para liberar e quantos programas abrem com a sessão |
| **02 Drivers** | Cada placa de vídeo e o driver em uso. Na NVIDIA: versão, se veio do **instalador .run** ou do **pacote do Ubuntu**, para quais kernels o módulo está compilado (DKMS), Secure Boot e o driver que o Ubuntu recomenda |
| **03 Atualizações** | apt, Flatpak, Snap e firmware (fwupd), e **Atualizar tudo** de uma vez |
| **04 Limpeza** | Kernels antigos (fica o atual e o anterior), pacotes que sobraram, instaladores do apt, Flatpaks sem uso, registros antigos do sistema, cache dos apps e a lixeira |
| **05 Inicialização** | Programas que abrem ao entrar na sessão e serviços do seu usuário, com liga e desliga |

## Driver da NVIDIA

- **Instalado pelo .run, com DKMS:** o módulo é recompilado sozinho quando o kernel atualiza. O Ripperdoc
  confere se ele está compilado para **todos** os kernels instalados. Se faltar um, oferece **Recompilar para todos
  os kernels** (instala os headers do kernel e roda o `dkms install`).
- **Trocar pelo pacote do Ubuntu:** remove o driver do .run e instala o recomendado pelo `ubuntu-drivers`, que
  passa a atualizar junto com o sistema. Se o pacote for **mais antigo** que o seu driver atual, o Ripperdoc avisa
  em vermelho: só vale a pena se o atual estiver dando problema.
- Kernel antigo sem o driver é **atenção** (só afeta quem escolher esse kernel no menu do GRUB). Kernel **mais novo**
  sem o driver é **crítico**: seria o próximo a iniciar, e a tela poderia ficar sem vídeo da NVIDIA.

## Inicialização

Desligar um programa da sessão cria uma cópia do atalho em `~/.config/autostart` com
`X-GNOME-Autostart-enabled=false`. Os arquivos do sistema em `/etc` não são tocados, e ligar de novo volta ao normal.

## Instalar

Pela **Arasaka Central** (Loja → Apps), ou:

```bash
./install.sh
```

Rode **sem sudo**. Para remover: `./uninstall.sh`.

---

Arasaka é marca da CD PROJEKT RED (projeto de fã, sem fins comerciais). A fonte `cedge1` usa a licença
FontStruct Non-Commercial.
