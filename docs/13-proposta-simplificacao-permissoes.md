# 13 — Proposta: simplificar a configuração de acesso dos usuários

Status: **aprovada pelo Julio em 18/10/2026 e implementada na v13.0.0** (não commitada; aguardando revisão do Astra).

Entregue: perfis prontos + Personalizado, páginas derivadas do universo, capacidades na mesma tela, prévia com diagnóstico, um botão com gravação atômica, limpeza (legado só leitura, formulários enxutos, textos corrigidos) e o item 6 (vale em até 1 minuto). A pergunta 1 (perfis) ficou como proposto: o caso Manutenção + Obras usa Personalizado.

Achados de segurança corrigidos no caminho: (a) "Sair" não limpava o cache de permissões, e o próximo usuário da mesma aba herdava o acesso; (b) a capacidade Upload não era checada, e "Dados e Qualidade" aparecia para qualquer usuário logado.

Correções pós-revisão do Astra (18/10/2026), todas cobertas por teste:
- B2/B3 (revalidação): a assinatura nova só é gravada depois de recarregar o usuário; se a recarga falhar, a sessão fica rebaixada (sem admin, sem capacidades) e tenta de novo em até 1 minuto, em vez de congelar o acesso antigo. A 1ª medição da sessão também descarta os caches.
- N1: falha ao ler o acesso no Neon não vira mais "Sem acesso". A tela mostra o erro e não desenha nem salva nada (antes, um clique em Salvar apagava o acesso real). `listar_escopos_universo` deixou de engolir a exceção.
- N2: negação legada de sub-página (contas, centro_custo...) e Upload negado com a capacidade ligada passam a ser detectados como Personalizado. A prévia respeita a negação legada. Decisão do Julio: salvar um perfil pronto APAGA as negações legadas (na mesma transação), com aviso na prévia. O mapa vive em `perfis.SUBPAGINAS_LEGADAS`.
- N3: o Personalizado tem um botão só, com gravação atômica (`salvar_perfil_acesso`). Universo em "Gerências específicas" sem nenhuma escolhida bloqueia o salvar. Saíram da lista de páginas `pce_especialista` (caixa Especialista do universo) e `upload` (capacidade Upload).

## Como é hoje

Para deixar uma pessoa vendo o que deve, o admin passa por **5 lugares, em 2 abas, com 4 botões de salvar diferentes**:

| # | Onde | O que define | Problema |
|---|---|---|---|
| 1 | Usuários › Criar | Papel, GG, Gerência | **Papel quase não tem efeito:** só `admin` libera algo; `gg` não é bypass. A Gerência gravada no usuário não é lida pelo RBAC. |
| 2 | Usuários › Editar | Ativo, Papel, Upload, Exportação, Justificativa macro/micro | Ok, mas fica longe do resto do acesso. |
| 3 | Permissões › Visão de páginas | 9 caixas, uma por página | **Duplica o universo:** a página só aparece se a caixa estiver marcada **e** o universo liberado. Liberar só uma das duas camadas deixa a tela em branco (caso Sandra). |
| 4 | Permissões › Acesso por universo | 3 universos × (vê? / GG inteira ou Gerências / lista) + caixa do Especialista | A caixa do Especialista **repete** a de páginas. OPEX e CAPEX Sustaining quase sempre levam a mesma lista de Gerências, cadastrada duas vezes. O texto diz "enforcement ainda não ligado", o que está **desatualizado**: ele está ligado desde a Fase RBAC-A.2. |
| 5 | Permissões › Escopos avançados (legado) | Pacote / CC / PEP Filho / Projeto | **Não faz nada:** grava linhas sem universo, que nenhuma tela lê. |

Além disso, qualquer mudança só vale **depois que a pessoa sai e entra de novo**.

## Proposta: um único "Perfil de acesso" por usuário

Uma tela só: escolher o usuário → escolher o perfil → ajustar o recorte → ver a prévia → **Salvar** (um botão).

**1. Perfis prontos.** Cada um já preenche universo, escopo e páginas:

| Perfil | Universos e escopo | Páginas | Capacidades padrão |
|---|---|---|---|
| Administrador | tudo | tudo + Gestão | todas |
| Gestão GG (consulta) | os 3 universos, GG inteira | Plano de Manutenção + Plano de Obras | exportar |
| Gerência de Manutenção | OPEX + CAPEX Sustaining nas **Gerências escolhidas** (uma lista só, vale para os dois) | Plano de Manutenção | exportar, justificar micro |
| Obras | CAPEX Obras nas Gerências de Obras e/ou Projetos escolhidos | Plano de Obras (+ Especialista, se marcado) | exportar |
| Personalizado | abre os controles avançados de hoje (sem o legado) | — | — |

**2. Páginas derivadas do universo.** Quem vê um universo vê as páginas dele. As caixas por página saem da tela principal e ficam só em "Personalizado", para **negar** uma página específica. Acaba o "liberou o universo mas esqueceu a página".

**3. Capacidades** (upload, exportar, justificar macro/micro) na mesma tela, como interruptores, com o padrão vindo do perfil.

**4. Prévia antes de salvar:** "Fulano vai ver: Resumo, Análise Financeira, Evidências SAP — recorte GER MALHA (SP)". Se o recorte não encontrar dado na base, aparece o mesmo aviso do diagnóstico "Perfis com problema".

**5. Limpeza:**
- tirar o "Escopos avançados (legado)" (vira só leitura, recolhido, enquanto existirem linhas antigas);
- tirar a Gerência do formulário de criar usuário;
- corrigir o texto desatualizado sobre o enforcement.

**6. (Opcional) Valer na hora:** gravar uma "versão de acesso" por usuário. Na próxima interação da pessoa, o app vê que a versão mudou e recarrega as permissões, sem precisar de novo login.

## O que NÃO muda

- O modelo de segurança: as mesmas tabelas (`app.escopo_acesso`, `app.permissao_pagina`, flags do usuário), o mesmo enforcement (`clausula_escopo`, `require_universo`, guards de página) e o fail-closed. O perfil é só um jeito mais curto de **gravar** as mesmas linhas.
- Usuários atuais: o perfil de cada um é **detectado** a partir do que já está gravado. Quem não se encaixa aparece como "Personalizado", sem perder nada.

## Esforço estimado e riscos

- Tela nova em `administracao.py` + função pura `perfil_para_linhas(perfil, recorte) -> (escopos, paginas, flags)` com testes. Dá para entregar sem mexer em `permissions.py`. O item 6 é o único que toca o login.
- Risco principal: derivar páginas do universo libera páginas que hoje estão negadas por caixa. A migração precisa preservar todo `permitido=false` explícito (o perfil vira "Personalizado").

## Decisões para o Julio
1. Os 4 perfis acima batem com quem usa o Fin360 hoje? Falta algum? (ex.: Gerente que só vê a própria Gerência, mas em Manutenção **e** Obras)
2. Quer o item 6 (valer sem novo login)?
