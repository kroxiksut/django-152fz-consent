from django.conf import settings
from django.db import models


class Course(models.Model):
    title = models.CharField("Название", max_length=200)
    slug = models.SlugField("Slug", max_length=220, unique=True)
    short_description = models.CharField("Краткое описание", max_length=255)
    description = models.TextField("Описание")
    starts_at = models.DateTimeField("Дата старта", null=True, blank=True)
    is_active = models.BooleanField("Активен", default=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"
        ordering = ("-is_active", "starts_at", "title")

    def __str__(self) -> str:
        return self.title


class CourseSignup(models.Model):
    full_name = models.CharField("ФИО", max_length=255)
    email = models.EmailField("Email")
    phone = models.CharField("Телефон", max_length=32)
    course = models.ForeignKey(
        Course,
        verbose_name="Курс",
        on_delete=models.PROTECT,
        related_name="signups",
    )
    comment = models.TextField("Комментарий", blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="course_signups",
    )
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Заявка на курс"
        verbose_name_plural = "Заявки на курс"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.full_name} -> {self.course}"


class ContactMessage(models.Model):
    full_name = models.CharField("ФИО", max_length=255)
    email = models.EmailField("Email")
    message = models.TextField("Сообщение")
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Сообщение обратной связи"
        verbose_name_plural = "Сообщения обратной связи"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"


class CertificateRequest(models.Model):
    full_name = models.CharField("ФИО", max_length=255)
    birth_date = models.DateField("Дата рождения")
    email = models.EmailField("Email")
    course_name = models.CharField("Курс", max_length=255)
    comment = models.TextField("Комментарий", blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="certificate_requests",
    )
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Заявка на сертификат"
        verbose_name_plural = "Заявки на сертификат"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.full_name} -> {self.course_name}"
