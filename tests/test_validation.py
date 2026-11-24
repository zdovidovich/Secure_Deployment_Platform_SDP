"""Тесты модуля валидации app/libs/validation.py."""

import io
import tarfile

import pytest

from libs.validation import (
    ValidationRule,
    parse_servers_from_form,
    validate_all_data,
    validate_form_data,
    validate_multiline_field,
    validate_ssh_private_key,
    validate_tar_archive,
    validate_telegram_chat_id,
)


# ---------------------------------------------------------------------------
# ValidationRule
# ---------------------------------------------------------------------------


class TestValidationRule:
    def test_required_empty_value_fails(self):
        rule = ValidationRule(r"^\d+$", "msg", required=True)
        ok, _ = rule.validate("")
        assert ok is False

    def test_optional_empty_value_passes_with_none(self):
        rule = ValidationRule(r"^\d+$", "msg", required=False)
        ok, value = rule.validate("   ")
        assert ok is True
        assert value is None

    def test_pattern_mismatch_fails(self):
        rule = ValidationRule(r"^[a-z]+$", "msg")
        ok, _ = rule.validate("ABC123")
        assert ok is False

    def test_pattern_match_returns_value(self):
        rule = ValidationRule(r"^[a-z]+$", "msg")
        ok, value = rule.validate("abc")
        assert ok is True
        assert value == "abc"

    def test_to_int_converts_valid_number(self):
        rule = ValidationRule(r"^\d+$", "msg", to_int=True)
        ok, value = rule.validate("8080")
        assert ok is True
        assert value == 8080

    def test_to_int_rejects_non_numeric(self):
        rule = ValidationRule(r"^\d+$", "msg", to_int=True)
        ok, _ = rule.validate("not-a-number")
        assert ok is False

    def test_max_length_500_enforced(self):
        rule = ValidationRule(r"^.*$", "msg")
        ok, _ = rule.validate("x" * 501)
        assert ok is False


# ---------------------------------------------------------------------------
# parse_servers_from_form — поддержка нескольких серверов
# ---------------------------------------------------------------------------


class TestParseServers:
    def test_single_server_scalar_fields_backcompat(self):
        form = {
            "ansible_host": "10.0.0.5",
            "ansible_port": "2222",
            "ansible_user": "admin",
        }
        servers, errors = parse_servers_from_form(form)
        assert errors == []
        assert servers == [{"host": "10.0.0.5", "port": 2222, "user": "admin"}]

    def test_multiple_servers(self):
        form = {
            "ansible_host": ["10.0.0.5", "10.0.0.6"],
            "ansible_port": ["22", "2222"],
            "ansible_user": ["ubuntu", "root"],
        }
        servers, errors = parse_servers_from_form(form)
        assert errors == []
        assert len(servers) == 2
        assert servers[1]["port"] == 2222

    def test_no_servers_returns_error(self):
        servers, errors = parse_servers_from_form({})
        assert servers == []
        assert "Не указано ни одного сервера" in errors

    def test_default_port_is_22(self):
        form = {"ansible_host": ["10.0.0.5"], "ansible_user": ["ubuntu"]}
        servers, errors = parse_servers_from_form(form)
        assert errors == []
        assert servers[0]["port"] == 22

    def test_invalid_ip_rejected(self):
        form = {
            "ansible_host": ["999.1.1.1"],
            "ansible_user": ["ubuntu"],
        }
        servers, errors = parse_servers_from_form(form)
        assert servers == []
        assert any("Неверный формат IP" in e for e in errors)

    def test_duplicate_ip_rejected(self):
        form = {
            "ansible_host": ["10.0.0.5", "10.0.0.5"],
            "ansible_user": ["a", "b"],
        }
        servers, errors = parse_servers_from_form(form)
        assert len(servers) == 1
        assert any("Дублирующийся" in e for e in errors)

    def test_port_out_of_range_rejected(self):
        form = {
            "ansible_host": ["10.0.0.5"],
            "ansible_port": ["70000"],
            "ansible_user": ["ubuntu"],
        }
        servers, errors = parse_servers_from_form(form)
        assert servers == []
        assert any("диапазоне 1-65535" in e for e in errors)

    def test_invalid_username_rejected(self):
        form = {
            "ansible_host": ["10.0.0.5"],
            "ansible_user": ["1bad!name"],
        }
        servers, errors = parse_servers_from_form(form)
        assert servers == []
        assert any("Неверный формат имени пользователя" in e for e in errors)

    def test_missing_user_rejected(self):
        form = {"ansible_host": ["10.0.0.5"]}
        servers, errors = parse_servers_from_form(form)
        assert servers == []
        assert any("Не указан пользователь" in e for e in errors)


# ---------------------------------------------------------------------------
# validate_form_data
# ---------------------------------------------------------------------------


class TestValidateFormData:
    def test_valid_minimal_form(self, valid_form_data):
        ok, errors, data = validate_form_data(valid_form_data)
        assert ok is True, errors
        assert data["app_host_port"] == 8080  # to_int преобразование
        assert data["image_source"] == "tar"

    def test_missing_required_container_name(self, valid_form_data):
        del valid_form_data["app_deploy_container_name"]
        ok, errors, _ = validate_form_data(valid_form_data)
        assert ok is False
        assert any("app_deploy_container_name" in e for e in errors)

    def test_invalid_image_name(self, valid_form_data):
        valid_form_data["app_deploy_image_name"] = ["bad image name!!"]
        ok, errors, _ = validate_form_data(valid_form_data)
        assert ok is False
        assert any("app_deploy_image_name" in e for e in errors)

    def test_registry_image_source_accepted(self, valid_form_data):
        valid_form_data["image_source"] = ["registry"]
        ok, _, data = validate_form_data(valid_form_data)
        assert ok is True
        assert data["image_source"] == "registry"

    def test_unknown_image_source_rejected(self, valid_form_data):
        valid_form_data["image_source"] = ["ftp"]
        ok, errors, _ = validate_form_data(valid_form_data)
        assert ok is False
        assert any("image_source" in e for e in errors)

    def test_port_range_checked(self, valid_form_data):
        valid_form_data["app_host_port"] = ["99999"]
        ok, errors, _ = validate_form_data(valid_form_data)
        assert ok is False
        assert any("app_host_port" in e for e in errors)

    def test_envs_parsed_to_dict(self, valid_form_data):
        valid_form_data["app_deploy_envs"] = ["KEY1=value1", "KEY2=value2"]
        ok, errors, data = validate_form_data(valid_form_data)
        assert ok is True, errors
        assert data["app_deploy_envs"] == {"KEY1": "value1", "KEY2": "value2"}

    def test_duplicate_env_keys_rejected(self, valid_form_data):
        valid_form_data["app_deploy_envs"] = ["KEY=a", "KEY=b"]
        ok, errors, _ = validate_form_data(valid_form_data)
        assert ok is False
        assert any("используется несколько раз" in e for e in errors)

    def test_volumes_list_parsed(self, valid_form_data):
        valid_form_data["app_deploy_volumes"] = ["/host:/container"]
        ok, errors, data = validate_form_data(valid_form_data)
        assert ok is True, errors
        assert data["app_deploy_volumes"] == ["/host:/container"]

    def test_duplicate_volume_host_rejected(self, valid_form_data):
        valid_form_data["app_deploy_volumes"] = ["/host:/c1", "/host:/c2"]
        ok, errors, _ = validate_form_data(valid_form_data)
        assert ok is False
        assert any("используется несколько раз" in e for e in errors)

    def test_cpus_format(self, valid_form_data):
        valid_form_data["app_deploy_cpus"] = ["1.5"]
        ok, _, _ = validate_form_data(valid_form_data)
        assert ok is True

        valid_form_data["app_deploy_cpus"] = ["1.3"]
        ok, _, _ = validate_form_data(valid_form_data)
        assert ok is False

    def test_memory_format(self, valid_form_data):
        valid_form_data["app_deploy_memory"] = ["512M"]
        ok, _, _ = validate_form_data(valid_form_data)
        assert ok is True

        valid_form_data["app_deploy_memory"] = ["512 MB"]
        ok, _, _ = validate_form_data(valid_form_data)
        assert ok is False


# ---------------------------------------------------------------------------
# validate_multiline_field / telegram chat id
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_multiline_required_empty(self):
        import re

        errors = validate_multiline_field(
            "", re.compile(r".*"), "field", required=True
        )
        assert errors and "обязательно" in errors[0]

    def test_multiline_skips_blank_lines(self):
        import re

        errors = validate_multiline_field(
            "\n\n  \n", re.compile(r"^\d+$"), "field"
        )
        assert errors == []

    @pytest.mark.parametrize(
        "value,valid",
        [
            ("", True),
            ("123456", True),
            ("-1001234567890", True),  # группа
            ("abc", False),
            ("12 34", False),
            ("1" * 21, False),
        ],
    )
    def test_telegram_chat_id(self, value, valid):
        errors = validate_telegram_chat_id({"telegram_chat_id": value})
        assert (errors == []) is valid


# ---------------------------------------------------------------------------
# validate_tar_archive / validate_ssh_private_key
# ---------------------------------------------------------------------------


class TestFileValidators:
    def test_valid_tar(self, docker_tar_file):
        assert validate_tar_archive(docker_tar_file) is True

    def test_invalid_tar(self, tmp_path):
        bad = tmp_path / "bad.tar"
        bad.write_bytes(b"this is not a tar archive")
        assert validate_tar_archive(str(bad)) is False

    def test_missing_file(self):
        assert validate_tar_archive("/nonexistent/path.tar") is False

    def test_valid_openssh_key(self, ssh_key_file):
        assert validate_ssh_private_key(ssh_key_file) is True

    def test_valid_pem_key(self, tmp_path):
        path = tmp_path / "id_rsa"
        path.write_text(
            "-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n"
        )
        assert validate_ssh_private_key(str(path)) is True

    def test_public_key_rejected(self, tmp_path):
        path = tmp_path / "id.pub"
        path.write_text("ssh-rsa AAAAB3... user@host\n")
        assert validate_ssh_private_key(str(path)) is False

    def test_empty_file_rejected(self, tmp_path):
        path = tmp_path / "empty"
        path.write_text("")
        assert validate_ssh_private_key(str(path)) is False

    def test_binary_file_rejected(self, tmp_path):
        path = tmp_path / "bin"
        path.write_bytes(b"\x00\x01\x02\x03")
        assert validate_ssh_private_key(str(path)) is False


# ---------------------------------------------------------------------------
# validate_all_data — интеграция всех проверок
# ---------------------------------------------------------------------------


class TestValidateAllData:
    def test_full_valid_flow(self, valid_form_data, docker_tar_file, ssh_key_file):
        ok, errors, data = validate_all_data(
            valid_form_data, docker_tar_file, ssh_key_file
        )
        assert ok is True, errors
        assert data["servers"][0]["host"] == "192.168.1.10"

    def test_missing_ssh_key(self, valid_form_data, docker_tar_file):
        ok, errors, _ = validate_all_data(valid_form_data, docker_tar_file, None)
        assert ok is False
        assert "Не загружен приватный SSH-ключ" in errors

    def test_tar_mode_requires_image(self, valid_form_data, ssh_key_file):
        ok, errors, _ = validate_all_data(valid_form_data, None, ssh_key_file)
        assert ok is False
        assert "Не загружен tar-архив с образом" in errors

    def test_registry_mode_without_tar_ok(self, valid_form_data, ssh_key_file):
        valid_form_data["image_source"] = ["registry"]
        ok, errors, _ = validate_all_data(valid_form_data, None, ssh_key_file)
        assert ok is True, errors

    def test_bad_ssh_key_content(self, valid_form_data, docker_tar_file, tmp_path):
        bad = tmp_path / "bad_key"
        bad.write_text("not a key at all\nsecond line\n")
        ok, errors, _ = validate_all_data(
            valid_form_data, docker_tar_file, str(bad)
        )
        assert ok is False
        assert any("ssh_key" in e for e in errors)

    def test_bad_tar_content(self, valid_form_data, ssh_key_file, tmp_path):
        bad = tmp_path / "bad.tar"
        bad.write_bytes(b"garbage")
        ok, errors, _ = validate_all_data(valid_form_data, str(bad), ssh_key_file)
        assert ok is False
        assert any("TAR" in e for e in errors)

    def test_invalid_server_propagates_error(self, valid_form_data, docker_tar_file, ssh_key_file):
        valid_form_data["ansible_host"] = ["1.2.3.400"]
        ok, errors, _ = validate_all_data(
            valid_form_data, docker_tar_file, ssh_key_file
        )
        assert ok is False
        assert any("Сервер 1" in e for e in errors)

    def test_invalid_telegram_chat_id_blocks(self, valid_form_data, docker_tar_file, ssh_key_file):
        valid_form_data["telegram_chat_id"] = ["not-a-number"]
        ok, errors, _ = validate_all_data(
            valid_form_data, docker_tar_file, ssh_key_file
        )
        assert ok is False
        assert any("telegram_chat_id" in e for e in errors)
