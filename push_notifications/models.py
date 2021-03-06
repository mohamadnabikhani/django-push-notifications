from __future__ import unicode_literals
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

from .fields import HexIntegerField
from .settings import PUSH_NOTIFICATIONS_SETTINGS as SETTINGS
from users.models import User

CLOUD_MESSAGE_TYPES = (
	("FCM", "Firebase Cloud Message"),

)


@python_2_unicode_compatible
class Device(models.Model):
	name = models.CharField(max_length=255, verbose_name=_("Name"), blank=True, null=True)
	active = models.BooleanField(
		verbose_name=_("Is active"), default=True,
		help_text=_("Inactive devices will not be sent notifications")
	)
	user = models.ForeignKey(
		User, blank=True, null=True, on_delete=models.CASCADE
	)
	date_created = models.DateTimeField(
		verbose_name=_("Creation date"), auto_now_add=True, null=True
	)
	application_id = models.CharField(
		max_length=64, verbose_name=_("Application ID"),
		help_text=_(
			"Opaque application identity, should be filled in for multiple"
			" key/certificate access"
		),
		blank=True, null=True
	)

	class Meta:
		abstract = True

	def __str__(self):
		return (
			self.name or str(self.device_id or "") or
			"%s for %s" % (self.__class__.__name__, self.user or "unknown user")
		)


class GCMDeviceManager(models.Manager):
	def get_queryset(self):
		return GCMDeviceQuerySet(self.model)


class GCMDeviceQuerySet(models.query.QuerySet):
	def send_message(self, message, **kwargs):
		if self:
			from .gcm import send_message as gcm_send_message

			data = kwargs.pop("extra", {})
			if message is not None:
				data["message"] = message

			app_ids = self.filter(active=True).values_list("application_id", flat=True).distinct()
			response = []
			for cloud_type in ("FCM", "GCM"):
				for app_id in app_ids:
					reg_ids = list(
						self.filter(
							active=True, cloud_message_type=cloud_type, application_id=app_id).values_list(
							"registration_id", flat=True
						)
					)
					if reg_ids:
						r = gcm_send_message(reg_ids, data, cloud_type, application_id=app_id, **kwargs)
						response.append(r)

			return response


class GCMDevice(Device):
	# device_id cannot be a reliable primary key as fragmentation between different devices
	# can make it turn out to be null and such:
	# http://android-developers.blogspot.co.uk/2011/03/identifying-app-installations.html
	device_id = HexIntegerField(
		verbose_name=_("Device ID"), blank=True, null=True, db_index=True,
		help_text=_("ANDROID_ID / TelephonyManager.getDeviceId() (always as hex)")
	)
	registration_id = models.TextField(verbose_name=_("Registration ID"))
	cloud_message_type = models.CharField(
		verbose_name=_("Cloud Message Type"), max_length=3,
		choices=CLOUD_MESSAGE_TYPES, default="FCM",
		help_text=_("You should choose FCM or GCM")
	)
	objects = GCMDeviceManager()

	class Meta:
		verbose_name = _("GCM device")

	def send_message(self, message, **kwargs):
		from .gcm import send_message as gcm_send_message

		data = kwargs.pop("extra", {})
		if message is not None:
			data["message"] = message

		return gcm_send_message(
			self.registration_id, data, self.cloud_message_type,
			application_id=self.application_id, **kwargs
		)


class APNSDeviceManager(models.Manager):
	def get_queryset(self):
		return APNSDeviceQuerySet(self.model)


class APNSDeviceQuerySet(models.query.QuerySet):
	def send_message(self, message, certfile=None, **kwargs):
		if self:
			from .apns import apns_send_bulk_message

			app_ids = self.filter(active=True).values_list("application_id", flat=True).distinct()
			res = []
			for app_id in app_ids:
				reg_ids = list(self.filter(active=True, application_id=app_id).values_list(
					"registration_id", flat=True)
				)
				r = apns_send_bulk_message(
					registration_ids=reg_ids, alert=message, application_id=app_id,
					certfile=certfile, **kwargs
				)
				if hasattr(r, "keys"):
					res += [r]
				elif hasattr(r, "__getitem__"):
					res += r
			return res


class APNSDevice(Device):
	device_id = models.UUIDField(
		verbose_name=_("Device ID"), blank=True, null=True, db_index=True,
		help_text="UDID / UIDevice.identifierForVendor()"
	)
	registration_id = models.CharField(
		verbose_name=_("Registration ID"), max_length=200, unique=True
	)

	objects = APNSDeviceManager()

	class Meta:
		verbose_name = _("APNS device")

	def send_message(self, message, certfile=None, **kwargs):
		from .apns import apns_send_message

		return apns_send_message(
			registration_id=self.registration_id,
			alert=message,
			application_id=self.application_id, certfile=certfile,
			**kwargs
		)


class WNSDeviceManager(models.Manager):
	def get_queryset(self):
		return WNSDeviceQuerySet(self.model)


class WNSDeviceQuerySet(models.query.QuerySet):
	def send_message(self, message, **kwargs):
		if self:
			from .wns import wns_send_bulk_message

			app_ids = self.filter(active=True).values_list("application_id", flat=True).distinct()
			res = []
			for app_id in app_ids:
				reg_ids = list(self.filter(active=True, application_id=app_id).values_list(
					"registration_id", flat=True
				))
				r = wns_send_bulk_message(uri_list=reg_ids, message=message, **kwargs)
				if hasattr(r, "keys"):
					res += [r]
				elif hasattr(r, "__getitem__"):
					res += r
			return res


class WNSDevice(Device):
	device_id = models.UUIDField(
		verbose_name=_("Device ID"), blank=True, null=True, db_index=True,
		help_text=_("GUID()")
	)
	registration_id = models.TextField(verbose_name=_("Notification URI"))

	objects = WNSDeviceManager()

	class Meta:
		verbose_name = _("WNS device")

	def send_message(self, message, **kwargs):
		from .wns import wns_send_message

		return wns_send_message(
			uri=self.registration_id, message=message, application_id=self.application_id, **kwargs
		)
