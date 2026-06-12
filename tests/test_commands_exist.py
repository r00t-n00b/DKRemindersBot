def test_commands_exist(main_module):
    assert hasattr(main_module, "start_command")
    assert hasattr(main_module, "help_command")
    assert hasattr(main_module, "remind_command")
    assert hasattr(main_module, "list_command")
    assert hasattr(main_module, "linkchat_command")