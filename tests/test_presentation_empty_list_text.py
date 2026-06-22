from presentation import format_empty_active_reminders_list_text


def test_empty_active_reminders_list_text_without_alias():
    assert (
        format_empty_active_reminders_list_text()
        == "Напоминаний нет.\n\n"
        "Напиши, например:\n"
        "напомни завтра в 18:00 купить молоко"
    )


def test_empty_active_reminders_list_text_with_alias():
    assert (
        format_empty_active_reminders_list_text(chat_alias="home")
        == "В чате 'home' напоминаний нет.\n\n"
        "Напиши, например:\n"
        "напомни завтра в 18:00 купить молоко"
    )
