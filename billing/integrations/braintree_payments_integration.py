from billing import Integration
from django.conf import settings
from django.views.decorators.http import require_GET
from billing.signals import transaction_was_successful, transaction_was_unsuccessful
from django.conf.urls.defaults import patterns, url
import braintree, urllib
from django.core.urlresolvers import reverse
from billing.forms.braintree_payments_forms import BraintreePaymentsForm

class BraintreePaymentsIntegration(Integration):
    def __init__(self, options=None):
        if not options:
            options = {}
        super(BraintreePaymentsIntegration, self).__init__(options=options)

        test_mode = getattr(settings, "MERCHANT_TEST_MODE", True)
        if test_mode:
            env = braintree.Environment.Sandbox
        else:
            env = braintree.Environment.Production
        braintree.Configuration.configure(
            env,
            settings.BRAINTREE_MERCHANT_ACCOUNT_ID,
            settings.BRAINTREE_PUBLIC_KEY,
            settings.BRAINTREE_PRIVATE_KEY
            )

    @property
    def service_url(self):
        return braintree.TransparentRedirect.url()

    def braintree_notify_handler(self, request):
        result = braintree.TransparentRedirect.confirm(urllib.urlencode(request.GET))
        if result.is_success:
            transaction_was_successful.send(sender=self,
                                            type="sale",
                                            response=result)
            return {"status": "SUCCESS", "response": result}
        transaction_was_unsuccessful.send(sender=self,
                                          type="sale",
                                          response=result)
        return {"status": "FAILURE": "response": result}

    def get_urls(self):
        urlpatterns = patterns('',
           url('^braintree-notify-handler/$', self.braintree_notify_handler, name="braintree_notify_handler"),)
        return urlpatterns

    def add_fields(self, params):
        for (key, val) in params.iteritems():
            if isinstance(val, dict):
                new_params = {}
                for k in val:
                    new_params["%s__%s" %(key, k)] = val[k]
                self.add_fields(new_params)
            else:
                self.add_field(key, val)

    def generate_tr_data(self):
        tr_data_dict = {"transaction": {}}
        tr_data_dict["transaction"]["type"] = self.fields["transaction__type"]
        tr_data_dict["transaction"]["order_id"] = self.fields["transaction__order_id"]
        if self.fields.get("transaction__customer_id"):
            tr_data_dict["transaction"]["customer_id"] = fields["transaction__customer__id"]
        if self.fields.get("transaction__customer__id"):
            tr_data_dict["transaction"]["customer"] = {"id": self.fields["transaction__customer__id"]}
        tr_data_dict["transaction"]["options"] = {"submit_for_settlement": 
                                                  self.fields.get("transaction__options__submit_for_settlement", True)}
        if self.fields.get("transaction__payment_method_token"):
            tr_data_dict["transaction"]["payment_method_token"] = self.fields["transaction__payment_method_token"]
        if self.fields.get("transaction__credit_card__token"):
            tr_data_dict["transaction"]["credit_card"] = {"token": self.fields["transaction__credit_card__token"]}
        if self.fields.get("transaction__amount"):
            tr_data_dict["transaction"]["amount"] = self.fields["transaction__amount"]
        tr_data = braintree.Transaction.tr_data_for_sale(tr_data_dict, reverse("braintree_notify_handler"))
        return tr_data

    def generate_form(self):
        initial_data = self.fields
        initial_data.update({"tr_data": self.generate_tr_data()})
        form = BraintreePaymentsForm(initial=initial_data)
        return form