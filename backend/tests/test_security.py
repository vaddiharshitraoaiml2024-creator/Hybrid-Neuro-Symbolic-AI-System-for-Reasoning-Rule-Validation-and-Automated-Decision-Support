import pytest
from app.security import safe_path,sanitize
def test_safe(): assert safe_path("src/main.py")=="src/main.py"
@pytest.mark.parametrize("p",["../x",".env","src/.env.local","node_modules/a","/tmp/x","key.pem"])
def test_blocked(p):
    with pytest.raises(ValueError): safe_path(p)
def test_sanitize(): assert sanitize({"README.md":"hello"})["README.md"]=="hello"
