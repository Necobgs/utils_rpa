"""Utilitários de resolução de captcha (Cloudflare Turnstile e ImageToText).

Este módulo expõe estratégias para resolver o Cloudflare Turnstile,
dependendo da ferramenta de automação em uso:

- :func:`cloudflare_solver_selenium`   — controla uma página via Selenium.
- :func:`cloudflare_solver_playwright`  — controla uma página via Playwright.

Além disso, mantém :func:`image_to_text`, que resolve captchas de imagem via
API do Anti-Captcha.

As dependências pesadas (selenium, playwright, anticaptchaofficial, aiohttp)
são importadas de forma preguiçosa dentro de cada função, de modo que importar
este módulo não exige tê-las todas instaladas — apenas o extra correspondente
ao método utilizado.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from selenium.webdriver.remote.webdriver import WebDriver

# ── Valores padrão (mesmos utilizados originalmente) ──────────────────────────

# XPath de um elemento cuja presença/visibilidade confirma que o captcha foi
# resolvido (o fluxo avançou). Por padrão, o campo de senha do login original.
XPATH_SUCCESS_ELEMENT = '//input[@id="idToken3"]'

# XPath que localiza o widget/iframe do Cloudflare Turnstile na página.
XPATH_CAPTCHA_WIDGET = "//*[@data-sitekey] | //iframe[contains(@src,'challenges.cloudflare.com')]"

# id de um elemento clicado no fallback para confirmar/submeter o token
# (não precisa ser um botão de login — qualquer elemento de confirmação serve).
ID_CONFIRMATION_ELEMENT = "loginButton_0"

# Trecho procurado no ``src`` do iframe do Turnstile.
IFRAME_SRC_MARKER = "challenges.cloudflare.com"

# Nome do atributo HTML que contém o sitekey do widget.
SITEKEY_ATTR = "data-sitekey"

# Timeouts (em segundos)
TIMEOUT_CAPTCHA_DETECT = 30   # Aguardando o widget do captcha aparecer
TIMEOUT_CLOUDFLARE_AUTO = 11  # Aguardando o Cloudflare resolver sozinho
TIMEOUT_SOLVER = 120          # Máximo aguardando o Anti-Captcha
TIMEOUT_INJECT_VALIDATE = 20  # Aguardando o elemento de sucesso após injetar o token

ENV_ANTICAPTCHA_KEY = "ANTICAPTCHA_KEY"

# Corpo do JavaScript de injeção do token na página. Usa a variável ``token``,
# que é fornecida de forma diferente por Selenium (arguments[0]) e Playwright
# (argumento da arrow function).
_INJECT_JS_BODY = """
    // 1. Preenche o input oculto na página PAI (não no iframe)
    var areas = document.querySelectorAll('input[name="cf-turnstile-response"]');
    areas.forEach(t => { t.value = token; });

    // 2. Descobre o callback registrado no elemento do widget e o chama
    var widget = document.querySelector('[data-sitekey]');
    var cbName = widget ? widget.getAttribute('data-callback') : null;
    if (cbName && typeof window[cbName] === 'function') {
        window[cbName](token);
        return 'callback:' + cbName;
    }

    // 3. Simula o postMessage que o iframe enviaria ao pai
    var widgetId = widget ? (widget.id || 'b227f') : 'b227f';
    window.dispatchEvent(new MessageEvent('message', {
        data: {
            source: 'cloudflare-challenge',
            widgetId: widgetId,
            event: 'turnstile-callback',
            token: token
        }
    }));

    // 4. Dispara eventos de input/change para ativar listeners do formulário
    areas.forEach(t => {
        ['input', 'change'].forEach(ev =>
            t.dispatchEvent(new Event(ev, { bubbles: true }))
        );
    });

    return 'postMessage+events';
"""

_INJECT_JS_SELENIUM = "var token = arguments[0];\n" + _INJECT_JS_BODY
_INJECT_JS_PLAYWRIGHT = "(token) => {\n" + _INJECT_JS_BODY + "\n}"

__all__ = [
    "CaptchaResult",
    "SolverRef",
    "cloudflare_solver_selenium",
    "cloudflare_solver_playwright",
    "image_to_text",
]


# ── Tipos tipados para compartilhamento entre threads ─────────────────────────

@dataclass
class CaptchaResult:
    """Carrega o resultado da thread do Anti-Captcha.

    Attributes:
        token: Token de resolução retornado pelo serviço (None enquanto pendente).
        error: Código/mensagem de erro, caso o solver falhe (None enquanto pendente).
    """

    token: str | None = None
    error: str | None = None


@dataclass
class SolverRef:
    """Guarda a referência ao solver em execução para permitir cancelamento remoto.

    Attributes:
        solver: Instância do turnstileProxyless (None antes de ser criado).
    """

    solver: Any = field(default=None, repr=False)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _get_logger(logger: logging.Logger | None) -> logging.Logger:
    return logger if logger is not None else logging.getLogger("__main__")


def _resolve_api_key(api_key: str | None, logger: logging.Logger) -> str:
    """Resolve a chave do Anti-Captcha, caindo para a variável de ambiente."""
    key = api_key if api_key is not None else os.getenv(ENV_ANTICAPTCHA_KEY, "")
    if not key:
        logger.warning(
            "[anti_captcha] ANTICAPTCHA_KEY não encontrada. "
            "A resolução automática poderá falhar."
        )
    return key


def _solve_in_thread(
    api_key: str,
    url: str,
    sitekey: str,
    result: CaptchaResult,
    solver_ref: SolverRef,
) -> None:
    """Envia o desafio Turnstile ao Anti-Captcha e aguarda o token de resposta.

    Grava o resultado (token ou erro) diretamente nos objetos passados por
    referência. Pode ser executado em thread separada ou de forma síncrona.

    Args:
        api_key: Chave da API do Anti-Captcha.
        url: URL da página onde o captcha está presente.
        sitekey: Chave pública do widget Turnstile.
        result: CaptchaResult compartilhado para gravar token/erro.
        solver_ref: SolverRef para guardar a instância (permite cancelar).
    """
    try:
        from anticaptchaofficial.turnstileproxyless import turnstileProxyless

        solver = turnstileProxyless()
        solver.set_verbose(1)
        solver.set_key(api_key)
        solver.set_website_url(url)
        solver.set_website_key(sitekey)

        # Grava referência antes de iniciar, para cancelamento externo
        solver_ref.solver = solver

        token = solver.solve_and_return_solution()

        if token != 0:
            result.token = token
        else:
            result.error = solver.error_code
    except Exception as e:  # noqa: BLE001 - queremos capturar qualquer falha do solver
        result.error = str(e)


def _extract_sitekey_from_src(src: str) -> str | None:
    if src and "sitekey=" in src:
        return src.split("sitekey=")[-1].split("&")[0]
    return None


# ── Resolução com Selenium ────────────────────────────────────────────────────

def cloudflare_solver_selenium(
    driver: WebDriver,
    *,
    api_key: str | None = None,
    xpath_success: str = XPATH_SUCCESS_ELEMENT,
    xpath_captcha_widget: str = XPATH_CAPTCHA_WIDGET,
    id_confirmation: str = ID_CONFIRMATION_ELEMENT,
    timeout_captcha_detect: int = TIMEOUT_CAPTCHA_DETECT,
    timeout_cloudflare_auto: int = TIMEOUT_CLOUDFLARE_AUTO,
    timeout_solver: int = TIMEOUT_SOLVER,
    timeout_inject_validate: int = TIMEOUT_INJECT_VALIDATE,
    logger: logging.Logger | None = None,
) -> bool:
    """Resolve o Cloudflare Turnstile controlando uma página via Selenium.

    Recebe o ``driver`` Selenium já inicializado (não cria nem fecha o driver).

    Args:
        driver: WebDriver do Selenium já posicionado na página do desafio.
        api_key: Chave do Anti-Captcha. Se ``None``, usa a variável de ambiente
            ``ANTICAPTCHA_KEY``.
        xpath_success: XPath de um elemento cuja presença indica que o captcha
            foi resolvido e o fluxo avançou (padrão: campo de senha ``idToken3``).
        xpath_captcha_widget: XPath para localizar o widget/iframe do Turnstile.
        id_confirmation: ``id`` de um elemento clicado no fallback para confirmar/
            submeter o token (não precisa ser um botão de login).
        timeout_captcha_detect: Segundos aguardando o widget aparecer.
        timeout_cloudflare_auto: Segundos aguardando resolução automática.
        timeout_solver: Segundos máximos aguardando o Anti-Captcha.
        timeout_inject_validate: Segundos aguardando validação após a injeção.
        logger: Logger opcional. Se ``None``, usa ``logging.getLogger("__main__")``.

    Returns:
        ``True`` se o captcha foi resolvido; ``False`` se o chamador deve
        reiniciar o fluxo.
    """
    from selenium.webdriver.common.by import By

    logger = _get_logger(logger)
    api_key = _resolve_api_key(api_key, logger)

    def _success_visible() -> bool:
        try:
            element = driver.find_element(By.XPATH, xpath_success)
            return element.is_displayed()
        except Exception:
            return False

    logger.info("[cloudflare_solver_selenium] Aguardando widget do captcha...")

    sitekey: str | None = None
    already_solved = False
    current_url: str | None = None

    # FASE 1: Detecta o que apareceu na tela
    for i in range(timeout_captcha_detect):
        if _success_visible():
            logger.info("[cloudflare_solver_selenium] Elemento de sucesso já visível.")
            already_solved = True
            break

        try:
            element = driver.find_element(By.XPATH, xpath_captcha_widget)
            sitekey = element.get_attribute(SITEKEY_ATTR) or _extract_sitekey_from_src(
                element.get_attribute("src") or ""
            )
            current_url = driver.current_url
            logger.info(f"[cloudflare_solver_selenium] Sitekey encontrado: {sitekey}")
            break
        except Exception:
            pass

        logger.debug(
            f"[cloudflare_solver_selenium] Aguardando... {i + 1}/{timeout_captcha_detect}s"
        )
        time.sleep(1)

    if already_solved:
        return True

    if not sitekey:
        logger.warning("[cloudflare_solver_selenium] Nada detectado. Sinal para reiniciar.")
        return False

    # FASE 2: Aguarda resolução automática do Cloudflare
    logger.info(
        f"[cloudflare_solver_selenium] Aguardando {timeout_cloudflare_auto}s "
        "para o Cloudflare resolver sozinho..."
    )
    solved_by_page = False
    for i in range(timeout_cloudflare_auto):
        if _success_visible():
            logger.info(
                f"[cloudflare_solver_selenium] Cloudflare resolveu automaticamente após {i + 1}s."
            )
            solved_by_page = True
            break
        time.sleep(1)

    if solved_by_page:
        return True

    # FASE 3: Aciona o Anti-Captcha em thread paralela
    logger.info("[cloudflare_solver_selenium] Acionando Anti-Captcha...")
    result = CaptchaResult()
    solver_ref = SolverRef()

    thread = threading.Thread(
        target=_solve_in_thread,
        args=(api_key, current_url, sitekey, result, solver_ref),
        daemon=True,
    )
    thread.start()

    # FASE 4: Monitora quem resolve primeiro
    for i in range(timeout_solver):
        if _success_visible():
            logger.info(
                f"[cloudflare_solver_selenium] Cloudflare resolveu após {i}s! Cancelando solver..."
            )
            solved_by_page = True
            if solver_ref.solver:
                try:
                    solver_ref.solver.report_incorrect_turnstile()
                    logger.info("[cloudflare_solver_selenium] Tarefa do Anti-Captcha cancelada.")
                except Exception:
                    pass
            break

        if result.token:
            logger.info(
                f"[cloudflare_solver_selenium] Token do Anti-Captcha recebido após {i}s."
            )
            break

        if result.error:
            logger.warning(f"[cloudflare_solver_selenium] Solver falhou: {result.error}")
            break

        time.sleep(1)

    # FASE 5: Avalia resultado final
    if not solved_by_page and not result.token:
        logger.error(
            "[cloudflare_solver_selenium] Nem a página nem o solver resolveram. Reiniciando."
        )
        return False

    # FASE 6: Injeta o token na página (apenas se veio do solver)
    if not solved_by_page and result.token:
        logger.info("[cloudflare_solver_selenium] Injetando token na página pai...")

        injection_method = driver.execute_script(_INJECT_JS_SELENIUM, result.token)

        logger.info(f"[cloudflare_solver_selenium] Método de injeção usado: {injection_method}")
        logger.info("[cloudflare_solver_selenium] Aguardando validação do token...")

        for i in range(timeout_inject_validate):
            if _success_visible():
                logger.info(
                    f"[cloudflare_solver_selenium] Elemento de sucesso confirmado após {i + 1}s."
                )
                return True
            time.sleep(1)

        logger.warning(
            "[cloudflare_solver_selenium] Elemento de sucesso não apareceu. "
            "Tentando confirmação manual..."
        )
        try:
            driver.find_element(By.ID, id_confirmation).click()
        except Exception:
            pass

        time.sleep(3)

        if not _success_visible():
            logger.error(
                "[cloudflare_solver_selenium] Elemento de sucesso ausente mesmo após confirmação "
                "manual. Token possivelmente inválido — reiniciando."
            )
            return False

    return True


# ── Resolução com Playwright ──────────────────────────────────────────────────

def cloudflare_solver_playwright(
    page: Page,
    *,
    api_key: str | None = None,
    xpath_success: str = XPATH_SUCCESS_ELEMENT,
    xpath_captcha_widget: str = XPATH_CAPTCHA_WIDGET,
    id_confirmation: str = ID_CONFIRMATION_ELEMENT,
    timeout_captcha_detect: int = TIMEOUT_CAPTCHA_DETECT,
    timeout_cloudflare_auto: int = TIMEOUT_CLOUDFLARE_AUTO,
    timeout_solver: int = TIMEOUT_SOLVER,
    timeout_inject_validate: int = TIMEOUT_INJECT_VALIDATE,
    logger: logging.Logger | None = None,
) -> bool:
    """Resolve o Cloudflare Turnstile controlando uma página via Playwright (sync API).

    Recebe a ``page`` do Playwright já inicializada (não cria nem fecha o browser).

    Args:
        page: ``Page`` do Playwright (sync API) já posicionada no desafio.
        api_key: Chave do Anti-Captcha. Se ``None``, usa a variável de ambiente
            ``ANTICAPTCHA_KEY``.
        xpath_success: XPath de um elemento cuja presença indica que o captcha
            foi resolvido e o fluxo avançou (padrão: campo de senha ``idToken3``).
        xpath_captcha_widget: XPath para localizar o widget/iframe do Turnstile.
        id_confirmation: ``id`` de um elemento clicado no fallback para confirmar/
            submeter o token (não precisa ser um botão de login).
        timeout_captcha_detect: Segundos aguardando o widget aparecer.
        timeout_cloudflare_auto: Segundos aguardando resolução automática.
        timeout_solver: Segundos máximos aguardando o Anti-Captcha.
        timeout_inject_validate: Segundos aguardando validação após a injeção.
        logger: Logger opcional. Se ``None``, usa ``logging.getLogger("__main__")``.

    Returns:
        ``True`` se o captcha foi resolvido; ``False`` se o chamador deve
        reiniciar o fluxo.
    """
    logger = _get_logger(logger)
    api_key = _resolve_api_key(api_key, logger)

    def _success_visible() -> bool:
        try:
            element = page.query_selector(f"xpath={xpath_success}")
            return element is not None and element.is_visible()
        except Exception:
            return False

    logger.info("[cloudflare_solver_playwright] Aguardando widget do captcha...")

    sitekey: str | None = None
    already_solved = False
    current_url: str | None = None

    # FASE 1: Detecta o que apareceu na tela
    for i in range(timeout_captcha_detect):
        if _success_visible():
            logger.info("[cloudflare_solver_playwright] Elemento de sucesso já visível.")
            already_solved = True
            break

        try:
            element = page.query_selector(f"xpath={xpath_captcha_widget}")
            if element is not None:
                sitekey = element.get_attribute(SITEKEY_ATTR) or _extract_sitekey_from_src(
                    element.get_attribute("src") or ""
                )
                current_url = page.url
                logger.info(
                    f"[cloudflare_solver_playwright] Sitekey encontrado: {sitekey}"
                )
                if sitekey:
                    break
        except Exception:
            pass

        logger.debug(
            f"[cloudflare_solver_playwright] Aguardando... {i + 1}/{timeout_captcha_detect}s"
        )
        time.sleep(1)

    if already_solved:
        return True

    if not sitekey:
        logger.warning("[cloudflare_solver_playwright] Nada detectado. Sinal para reiniciar.")
        return False

    # FASE 2: Aguarda resolução automática do Cloudflare
    logger.info(
        f"[cloudflare_solver_playwright] Aguardando {timeout_cloudflare_auto}s "
        "para o Cloudflare resolver sozinho..."
    )
    solved_by_page = False
    for i in range(timeout_cloudflare_auto):
        if _success_visible():
            logger.info(
                f"[cloudflare_solver_playwright] Cloudflare resolveu automaticamente após {i + 1}s."
            )
            solved_by_page = True
            break
        time.sleep(1)

    if solved_by_page:
        return True

    # FASE 3: Aciona o Anti-Captcha em thread paralela
    logger.info("[cloudflare_solver_playwright] Acionando Anti-Captcha...")
    result = CaptchaResult()
    solver_ref = SolverRef()

    thread = threading.Thread(
        target=_solve_in_thread,
        args=(api_key, current_url, sitekey, result, solver_ref),
        daemon=True,
    )
    thread.start()

    # FASE 4: Monitora quem resolve primeiro
    for i in range(timeout_solver):
        if _success_visible():
            logger.info(
                f"[cloudflare_solver_playwright] Cloudflare resolveu após {i}s! "
                "Cancelando solver..."
            )
            solved_by_page = True
            if solver_ref.solver:
                try:
                    solver_ref.solver.report_incorrect_turnstile()
                    logger.info("[cloudflare_solver_playwright] Tarefa do Anti-Captcha cancelada.")
                except Exception:
                    pass
            break

        if result.token:
            logger.info(
                f"[cloudflare_solver_playwright] Token do Anti-Captcha recebido após {i}s."
            )
            break

        if result.error:
            logger.warning(f"[cloudflare_solver_playwright] Solver falhou: {result.error}")
            break

        time.sleep(1)

    # FASE 5: Avalia resultado final
    if not solved_by_page and not result.token:
        logger.error(
            "[cloudflare_solver_playwright] Nem a página nem o solver resolveram. Reiniciando."
        )
        return False

    # FASE 6: Injeta o token na página (apenas se veio do solver)
    if not solved_by_page and result.token:
        logger.info("[cloudflare_solver_playwright] Injetando token na página pai...")

        injection_method = page.evaluate(_INJECT_JS_PLAYWRIGHT, result.token)

        logger.info(f"[cloudflare_solver_playwright] Método de injeção usado: {injection_method}")
        logger.info("[cloudflare_solver_playwright] Aguardando validação do token...")

        for i in range(timeout_inject_validate):
            if _success_visible():
                logger.info(
                    f"[cloudflare_solver_playwright] Elemento de sucesso confirmado após {i + 1}s."
                )
                return True
            time.sleep(1)

        logger.warning(
            "[cloudflare_solver_playwright] Elemento de sucesso não apareceu. "
            "Tentando confirmação manual..."
        )
        try:
            page.click(f"#{id_confirmation}")
        except Exception:
            pass

        time.sleep(3)

        if not _success_visible():
            logger.error(
                "[cloudflare_solver_playwright] Elemento de sucesso ausente mesmo após confirmação "
                "manual. Token possivelmente inválido — reiniciando."
            )
            return False

    return True


# ── Resolução de captcha de imagem (ImageToText) ──────────────────────────────

async def image_to_text(api_key: str, base64_image: str, loops_response: int = 120) -> str:
    """Converte uma imagem em texto utilizando a API do Anti-Captcha.

    Args:
        api_key: Chave da API do Anti-Captcha.
        base64_image: Imagem em base64.
        loops_response: Quantidade de loops para verificar o resultado do captcha.

    Returns:
        String do texto da imagem.

    Raises:
        Exception: Se o captcha não for resolvido ou a API retornar erro.
    """
    from asyncio import sleep

    from aiohttp import ClientSession

    if not api_key or not api_key.strip():
        raise Exception("api_key não encontrada")
    if not base64_image or not base64_image.strip():
        raise Exception("BASE64_IMAGE do captcha ausente ou inválida")

    create_task_payload = {
        "clientKey": api_key,
        "task": {
            "type": "ImageToTextTask",
            "body": base64_image,
            "phrase": False,
            "case": False,
            "numeric": False,
            "math": False,
            "minLength": 0,
            "maxLength": 0,
        },
        "softId": 0,
    }

    async with ClientSession() as client:
        async with client.post(
            "https://api.anti-captcha.com/createTask",
            json=create_task_payload,
            timeout=60.0,
        ) as response:
            response.raise_for_status()
            response_json = await response.json()

        if response_json.get("errorId", 0) != 0:
            raise Exception(
                f"Não foi possível resolver o captcha: {response_json.get('errorDescription')}"
            )

        task_id = response_json.get("taskId")
        if not task_id:
            raise Exception("Captcha não retornou um taskId.")

        for _ in range(loops_response):
            await sleep(1)
            result_payload = {"clientKey": api_key, "taskId": task_id}
            async with client.post(
                "https://api.anti-captcha.com/getTaskResult",
                json=result_payload,
                timeout=120.0,
            ) as result_response:
                result_response.raise_for_status()
                result_json = await result_response.json()

            if result_json.get("errorId", 0) != 0:
                raise Exception(f"getTaskResult error: {result_json.get('errorDescription')}")

            if result_json.get("status") == "ready":
                solution = result_json.get("solution", {}).get("text")
                if solution:
                    return solution
                raise Exception("Captcha retornou uma solução vazia.")

        raise Exception("Tempo limite de resolução do captcha excedido.")
