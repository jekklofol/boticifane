"""
find_leak.py — найти чей ключ зашит в слитом скрипте.

Использование:
    python find_leak.py leaked_script.lua
    python find_leak.py  (вставь код вручную)
"""

import sys
import re
import db_v2


def decode_pd(numbers: list[int]) -> str:
    """Обратная операция к _pd() в Lua: XOR с позиционным ключом."""
    result = []
    for i, n in enumerate(numbers):
        result.append(chr(n ^ ((i * 17 + 5) % 97 + 3)))
    return "".join(result)


def extract_pd_calls(lua_code: str) -> list[str]:
    """Найти все _pd({...}) вызовы в коде и декодировать их."""
    pattern = r'_pd\(\{([0-9,\s]+)\}\)'
    results = []
    for match in re.finditer(pattern, lua_code):
        raw = match.group(1)
        try:
            numbers = [int(x.strip()) for x in raw.split(",") if x.strip()]
            decoded = decode_pd(numbers)
            results.append(decoded)
        except Exception:
            pass
    return results


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                code = f.read()
        except FileNotFoundError:
            print(f"[!] Файл не найден: {path}")
            sys.exit(1)
    else:
        print("Вставь содержимое слитого скрипта (Ctrl+Z Enter для завершения):")
        code = sys.stdin.read()

    print("\n── Декодированные строки из скрипта ──────────────────────────")
    decoded = extract_pd_calls(code)
    if not decoded:
        print("[!] _pd() вызовов не найдено. Скрипт может быть без инжекции.")
        sys.exit(0)

    for s in decoded:
        print(f"  {repr(s)}")

    # Ищем ключ в БД
    print("\n── Поиск по базе данных ──────────────────────────────────────")
    db_v2.init_db()
    found = False
    for s in decoded:
        # Ключи обычно выглядят как PD-XXXX-XXXX или UUID
        lic = db_v2.get_license(s)
        if lic:
            found = True
            print(f"\n🔑 КЛЮЧ НАЙДЕН: {s}")
            print(f"   Статус:      {lic['status']}")
            print(f"   Telegram ID: {lic['tg_id']}")
            print(f"   Roblox:      {lic['roblox_name']} (uid: {lic['roblox_user_id']})")
            print(f"   Активирован: {lic['activated_at']}")
            print(f"\n   Забанить: python find_leak.py --ban {s}")

    if not found:
        print("[?] Ключ не найден в БД. Возможно скрипт старый или ключ уже удалён.")

    # Обработка --ban флага
    if "--ban" in sys.argv:
        idx = sys.argv.index("--ban")
        if idx + 1 < len(sys.argv):
            ban_key = sys.argv[idx + 1]
            lic = db_v2.get_license(ban_key)
            if lic:
                db_v2.revoke_license(ban_key)
                print(f"\n🚫 Ключ {ban_key} заблокирован.")
                print(f"   Пользователь {lic['roblox_name']} (TG: {lic['tg_id']}) больше не получит скрипт.")
            else:
                print(f"[!] Ключ {ban_key} не найден в БД.")


if __name__ == "__main__":
    main()
