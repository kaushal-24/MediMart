# Generated for the beginner MediMart Phase 3 setup.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Brand",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("slug", models.SlugField(blank=True, max_length=140, unique=True)),
                ("logo", models.ImageField(blank=True, null=True, upload_to="brands/")),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(blank=True, max_length=140, unique=True)),
                ("description", models.TextField(blank=True)),
                ("image", models.ImageField(blank=True, null=True, upload_to="categories/")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="children",
                        to="products.category",
                    ),
                ),
            ],
            options={"verbose_name_plural": "categories", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=180)),
                ("slug", models.SlugField(blank=True, max_length=220, unique=True)),
                ("sku", models.CharField(max_length=60, unique=True)),
                (
                    "product_type",
                    models.CharField(
                        choices=[
                            ("medicine", "Medicine"),
                            ("medical_equipment", "Medical Equipment"),
                            ("surgical_equipment", "Surgical Equipment"),
                            ("diagnostic_equipment", "Diagnostic Equipment"),
                            ("healthcare_product", "Healthcare Product"),
                            ("personal_care", "Personal Care"),
                            ("supplement", "Supplement"),
                            ("baby_care", "Baby Care"),
                            ("fitness_equipment", "Fitness Equipment"),
                            ("orthopedic_product", "Orthopedic Product"),
                            ("first_aid", "First Aid"),
                            ("lab_equipment", "Lab Equipment"),
                        ],
                        max_length=40,
                    ),
                ),
                ("image", models.ImageField(blank=True, null=True, upload_to="products/")),
                ("short_description", models.CharField(blank=True, max_length=255)),
                ("description", models.TextField()),
                ("mrp", models.DecimalField(decimal_places=2, max_digits=10)),
                ("selling_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("stock_quantity", models.PositiveIntegerField(default=0)),
                ("requires_prescription", models.BooleanField(default=False)),
                ("manufacturer", models.CharField(blank=True, max_length=160)),
                ("composition", models.CharField(blank=True, max_length=255)),
                ("pack_size", models.CharField(blank=True, max_length=80)),
                ("unit", models.CharField(blank=True, max_length=40)),
                ("weight", models.CharField(blank=True, max_length=80)),
                ("dimensions", models.CharField(blank=True, max_length=120)),
                ("seo_title", models.CharField(blank=True, max_length=180)),
                ("seo_description", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("is_featured", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "brand",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="products",
                        to="products.brand",
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="products",
                        to="products.category",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ProductImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="products/gallery/")),
                ("alt_text", models.CharField(blank=True, max_length=150)),
                ("is_primary", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="products.product",
                    ),
                ),
            ],
            options={"ordering": ["-is_primary", "id"]},
        ),
        migrations.CreateModel(
            name="ProductSpecification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("value", models.CharField(max_length=255)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="specifications",
                        to="products.product",
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
    ]
