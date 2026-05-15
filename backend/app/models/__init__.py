# Import all models here so Alembic autogenerate can detect them.
from app.models.tenant import Tenant  # noqa: F401
from app.models.user import User, PasswordResetToken, LoginLog  # noqa: F401
from app.models.email_config import TenantEmailConfig  # noqa: F401
from app.models.department import Department  # noqa: F401
from app.models.service import ServiceCategory, Service  # noqa: F401
from app.models.provider import Provider  # noqa: F401
from app.models.schedule import ProviderSchedule, ProviderScheduleException, TenantOperatingHours  # noqa: F401
from app.models.station import Station  # noqa: F401
from app.models.provider_service_price import ProviderServicePrice  # noqa: F401
from app.models.client import ClientHousehold, Client  # noqa: F401
from app.models.appointment import (  # noqa: F401
    AppointmentRequest,
    AppointmentRequestItem,
    Appointment,
    AppointmentItem,
    AppointmentReminder,
)
from app.models.payment_method import TenantPaymentMethod, PaymentMethodKind  # noqa: F401
from app.models.sale import Sale, SaleAppointment, SaleItem, Payment, SaleStatus  # noqa: F401
from app.models.time_block import TimeBlock  # noqa: F401
from app.models.cash_reconciliation import CashReconciliation, PettyCashEntry, ReconciliationStatus  # noqa: F401
from app.models.promotion import TenantPromotion, PromotionKind  # noqa: F401
from app.models.retail import RetailItem, RetailStockMovement  # noqa: F401
from app.models.i18n import ServiceCategoryTranslation, ServiceTranslation, RetailItemTranslation  # noqa: F401
from app.models.staff_time_entry import StaffTimeEntry  # noqa: F401
from app.models.acknowledgement import TenantAcknowledgement  # noqa: F401
