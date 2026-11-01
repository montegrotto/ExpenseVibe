from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("E-postadress krävs")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_admin", True)
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("E-post", unique=True)
    first_name = models.CharField("Förnamn", max_length=150, blank=True)
    last_name = models.CharField("Efternamn", max_length=150, blank=True)

    # Primär matchningsnyckel mot Visma Lön 600 (EmploymentNo i tidsredovisnings-
    # filen) - se export/services.py. Personnummer är där bara valfritt, till
    # skillnad från anställningsnumret som Visma kräver för att hitta rätt anställd.
    employment_number = models.CharField("Anställningsnummer", max_length=20, unique=True)
    personal_identity_number = models.CharField("Personnummer", max_length=12, blank=True)

    is_approver = models.BooleanField("Attestant", default=False)
    is_admin = models.BooleanField("Administratör", default=False)

    # Sätts varje gång admin skapar användaren eller (åter)sätter lösenordet,
    # se core.middleware.ForcePasswordChangeMiddleware.
    must_change_password = models.BooleanField("Måste byta lösenord", default=True)

    is_active = models.BooleanField("Aktiv", default=True)
    is_staff = models.BooleanField("Åtkomst till Django-admin", default=False)
    date_joined = models.DateTimeField("Skapad", auto_now_add=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["employment_number"]

    class Meta:
        verbose_name = "Användare"
        verbose_name_plural = "Användare"
        ordering = ["first_name", "last_name", "email"]

    def __str__(self):
        return self.get_full_name() or self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name or self.email
