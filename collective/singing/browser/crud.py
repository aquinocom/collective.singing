from zope import interface
import zope.event
import zope.lifecycleevent
from z3c.form import button
from z3c.form import field
from z3c.form import form
import z3c.form.widget
from z3c.form.interfaces import DISPLAY_MODE, INPUT_MODE, NOVALUE
from zope.app.pagetemplate import viewpagetemplatefile

from collective.singing import MessageFactory as _
from collective.singing.browser.widget import SingleCheckboxWidget

class ICrudForm(interface.Interface):

    update_schema = interface.Attribute(
        "Editable part of the schema for use in the update form.")

    view_schema = interface.Attribute(
        "Viewable (only) part of the schema for use in the update form.")

    add_schema = interface.Attribute(
        "Schema for use in the add form; defaults to ``update_schema``.")

    def get_items():
        """Subclasses must a list of all items to edit.

        This list contains tuples of the form ``(id, item)``, where
        the id is a unique identifiers to the items.  The items must
        be adaptable to the schema returned by ``update_schema`` and
        ``view_schema`` methods.
        """

    def add(data):
        """Subclasses must implement this method to create an item for
        the given `data` *and* add it to a container, and return it.

        The `data` mapping corresponds to the schema returned by
        `add_schema`.
        """

    def remove((id, item)):
        """Subclasses must implement this method to remove the given
        item from the site.

        It's left to the implementing class to notify of
        ``zope.app.container.contained.ObjectRemovedEvent``.
        """

    def before_update(item, data):
        """A hook that gets called before an item is updated.
        """

    def link(item):
        """Return a URL for the item or None.
        """

class AbstractCrudForm(object):
    """The AbstractCrudForm is not a form but implements methods
    necessary to comply with the ``ICrudForm`` interface:
    
      >>> from zope.interface.verify import verifyClass
      >>> verifyClass(ICrudForm, AbstractCrudForm)
      True
    """
    interface.implements(ICrudForm)

    update_schema = None # subclasses must implement this
    view_schema = None

    @property
    def add_schema(self):
        return self.update_schema

    def get_items(self):
        raise NotImplementedError

    def add(self, data):
        raise NotImplementedError

    def remove(self, (id, item)):
        raise NotImplementedError

    def before_update(self, item, data):
        pass

    def link(self, item):
        return None

class EditSubForm(form.EditForm):
    template = viewpagetemplatefile.ViewPageTemplateFile('crud-row.pt')

    @property
    def prefix(self):
        return 'crud-edit.%s.' % self.content_id

    # These are set by the parent form
    content = None
    content_id = None

    @property
    def fields(self):
        fields = field.Fields(self._select_field())
        update_fields = field.Fields(self.context.context.update_schema)
        view_schema = self.context.context.view_schema

        if view_schema:
            view_fields = field.Fields(view_schema)
            for f in view_fields.values():
                f.mode = DISPLAY_MODE
                # This is to allow a field to appear in both view
                # and edit mode at the same time:
                f.__name__ = 'view_' + f.__name__

            fields += view_fields
            
        fields += update_fields

        return fields

    def getContent(self):
        return self.content

    def _select_field(self):
        @zope.interface.implementer(z3c.form.interfaces.IDataConverter)
        def select_widget_factory(field, request):
            widget = SingleCheckboxWidget(request)
            return z3c.form.widget.FieldWidget(field, widget)

        select_field = field.Field(
            zope.schema.Bool(__name__='select',
                             required=False,
                             title=_(u'select')))
        select_field.widgetFactory[INPUT_MODE] = select_widget_factory
        return select_field

class EditForm(form.Form):
    label = _(u"Edit")
    template = viewpagetemplatefile.ViewPageTemplateFile('crud-table.pt')
    prefix = 'crud-edit.'
    
    def update(self):
        self._update_subforms()
        super(EditForm, self).update()

    def _update_subforms(self):
        self.subforms = []
        for id, item in self.context.get_items():
            subform = EditSubForm(self, self.request)
            subform.content = item
            subform.content_id = id
            subform.update()
            self.subforms.append(subform)

    @button.buttonAndHandler(_('Apply changes'), name='edit')
    def handle_edit(self, action):
        self.status = _(u"No changes made.")
        for subform in self.subforms:
            data, errors = subform.extractData()
            if errors:
                self.status = subform.formErrorsMessage
                continue
            del data['select']
            self.context.before_update(subform.content, data)
            changes = subform.applyChanges(data)
            if changes:
                self.status = _(u"Successfully updated.")

    @button.buttonAndHandler(_('Delete'), name='delete')
    def handle_delete(self, action):
        self.status = _(u"Please select items to delete.")

        for subform in self.subforms:
            data = subform.widgets['select'].extract()
            if not data or data is NOVALUE:
                continue
            else:
                self.context.remove((subform.content_id, subform.content))
                self.status = _(u"Successfully deleted items.")

        # We changed the amount of entries, so we update the subforms again.
        self._update_subforms()

class AddForm(form.Form):
    label = _(u"Add")
    template = viewpagetemplatefile.ViewPageTemplateFile('form.pt')
    prefix = 'crud-add.'
    ignoreContext = True
    ignoreRequest = True

    @property
    def fields(self):
        return field.Fields(self.context.add_schema)

    @button.buttonAndHandler(_('Add'), name='add')
    def handle_add(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = form.AddForm.formErrorsMessage
            return
        item = self.context.add(data)
        zope.event.notify(zope.lifecycleevent.ObjectCreatedEvent(item))
        self.status = _(u"Item added successfully.")

class CrudForm(AbstractCrudForm, form.Form):
    template = viewpagetemplatefile.ViewPageTemplateFile('form-master.pt')

    editform_factory = EditForm
    addform_factory = AddForm

    def update(self):
        super(CrudForm, self).update()

        addform = self.addform_factory(self, self.request)
        editform = self.editform_factory(self, self.request)
        addform.update()
        editform.update()
        self.subforms = [editform, addform]
