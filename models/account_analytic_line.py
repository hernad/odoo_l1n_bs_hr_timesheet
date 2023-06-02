from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta

class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    default_project_id = fields.Integer(compute='_default_project_id', store=False)
    default_task_id = fields.Integer(compute='_default_task_id', store=False)
    default_date = fields.Date(compute='_default_date', store=False)
    default_work_type_id = fields.Integer(compute='_default_work_type_id', store=False)
    default_unit_amount = fields.Float(compute='_default_unit_amount', store=False)
    default_employee_id = fields.Integer(compute='_default_employee_id', store=False)


    in_payroll = fields.Date(
       string="Plata", 
       compute="_calc_in_payroll",
       search="_search_in_payroll"
    )
    work_type_id = fields.Many2one(string="Work Type",
                                   comodel_name="hr.timesheet.work_type",
                                   help="Odaberi vrstu rada",
                                   required=True)

    work_type_code = fields.Char('Work type code', compute='_compute_work_type_code')

    # worked_days_id = fields.Many2one(string="Payslip",
    #                                 comodel_name="hr.payslip.worked_days")

    worked_days_ids = fields.Many2many(
        string="Worked days",
        comodel_name="hr.payslip.worked_days",
        relation="hr_payslip_analytic_rel",
        # model records
        column1="analytic_line_id",
        # related model records
        column2="worked_days_id",
        inverse_name="timesheet_item_ids"
    )
 
    def set_default_data_entry_values(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'user.timesheet.options.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [[False, 'form']],
            'target': 'new',
        }

    @api.model
    def default_get(self, fields_list):
    
        values = super().default_get(fields_list)
        user_options = self.env["res.users.options"].search([
            ('user_id', '=', self.env.user.id)
        ])
    
        if user_options:
            values.update({        
                "project_id": user_options.data_entry_project_id,
                "task_id": user_options.data_entry_task_id,
                "date": user_options.data_entry_date,
                "employee_id": user_options.data_entry_employee_id,
                "work_type_id": user_options.data_entry_work_type_id,
                "unit_amount": user_options.data_entry_unit_amount
                #"name": self.env.user.name
            })

        return values

    @api.model
    def create(self, vals):
        acc_line = super(AccountAnalyticLine, self).create(vals)
        return acc_line

    def write(self, vals):
        if any(in_payroll for in_payroll in set(self.mapped('in_payroll'))):
            raise UserError(_("Šihtarica iskorištena u obračunu - ne čačkaj mečku!"))
        else:
            if len(self.mapped('date')) > 0:
                user_options = self.env["res.users.options"].search([
                    ('user_id', '=', self.env.user.id)
                ])
                if user_options:
                    user_options.write({
                        "data_entry_date": max(self.mapped('date')) + timedelta(days=1),
                    })

            return super(AccountAnalyticLine, self).write(vals)

    def _default_project_id(self):
       if 'project_id' in self.default_get([]) and 'id' in self.default_get([])['project_id']:
          self.default_project_id = self.default_get([])['project_id'].id
       else:
          self.default_project_id = False
       return

    def _default_task_id(self):
       if 'task_id' in self.default_get([]) and 'id' in self.default_get([])['task_id']:
          self.default_task_id = self.default_get([])['task_id'].id
       else:
          self.default_task_id = False
       return

    def _default_date(self):
       if 'date' in self.default_get([]):
          self.default_date = self.default_get([])['date']
       else:
          self.default_date = False
       return

    def _default_employee_id(self):
        if 'employee_id' in self.default_get([]):
           self.default_employee_id = self.default_get([])['employee_id']
        else:
           self.default_employee_id = False
        return


    def _default_work_type_id(self):
        if 'work_type_id' in self.default_get([]):
           self.default_work_type_id = self.default_get([])['work_type_id']
        else:
           self.default_work_type_id = False
        return


    def _default_unit_amount(self):
        if 'unit_amount' in self.default_get([]):
           self.default_unit_amount = self.default_get([])['unit_amount']
        else:
           self.default_unit_amount = False
        return

    @api.depends('work_type_id')
    def _compute_work_type_code(self):
        for rec in self:
            rec.work_type_code = rec.work_type_id.code

    @api.depends('worked_days_ids')
    # timesheet item spent in payroll
    def _calc_in_payroll(self):
        for rec in self:
            if rec.worked_days_ids:
                rec.in_payroll = rec.worked_days_ids[0].payslip_id.date_to
            else:
                rec.in_payroll = False

    def unlink(self):
        for rec in self:
            if rec.in_payroll:
                raise(ValidationError("Šihtarica iskorištena u obračunu se ne može brisati!"))
        return super(AccountAnalyticLine, self).unlink()


    def split_as_needed(self, hours_to_spend, food_days_rest):
        amount_to_split = self.unit_amount
        name_to_split = self.name.strip()
        work_type_id_1 = self.work_type_id
        work_type_id_2 = work_type_id_1

        if hours_to_spend > 0 and hours_to_spend < amount_to_split:
            work_type_old = work_type_id_1
            if work_type_old.food_included:
                env_db_work_type = self.env['hr.timesheet.work_type']
                if work_type_old.code == "10_SF":
                    work_type_new = env_db_work_type.search([("code", '=', '11_S')])
                elif work_type_old.code == "20_NF":
                    work_type_new = env_db_work_type.search([("code", '=', '21_N')])
                elif work_type_old.code == "30_WF":
                    work_type_new = env_db_work_type.search([("code", '=', '31_W')])
                else:
                    raise(ValidationError('Način rada: ' + work_type_old.code + ' mora imati varijantu bez TO'))

                if food_days_rest <= 0:
                    # we have reached food days limit
                    work_type_id_1 = work_type_new
                    work_type_id_2 = work_type_old
                else:
                    work_type_id_1 = work_type_old
                    work_type_id_2 = work_type_new

            self.write({
                    'unit_amount': hours_to_spend,
                    'name': 'split1: ' + name_to_split,
                    'work_type_id': work_type_id_1.id
            })
            self.copy({
                'unit_amount': amount_to_split - hours_to_spend,
                'name': 'split2: ' + name_to_split,
                'work_type_id': work_type_id_2.id
            })

        return


    # @api.constrains('unit_amount')
    # def _check_unit_amount(self):
    #  #if not isinstance(self.ancestor_task_id, models.BaseModel):
    #  #   return
    #  for rec in self:
    #     if rec.unit_amount < 1:
    #           raise ValidationError(_('Broj sati mora biti > 0'))

    # def write(self, vals):
    #    #if 'unit_amount' in vals:
    #    if self.unit_amount < 1:
    #       raise UserError(_('Belaj sihtarica sati < 0.'))
    #    return super(AccountAnalyticLine, self).write(vals)


    # analytic_line unit_amount = 8, hours_to_spend = 3
    # => we need two analytic lines: 3 + 5


    def _search_in_payroll(self, operator, value):
        if operator == '=':
           recs = self.search([]).filtered(lambda x: x.in_payroll == value)
        elif operator == '!=':
           recs = self.search([]).filtered(lambda x: x.in_payroll != value)
        else:
           # npr '@' - sadrzi
           #recs = self.search([]).filtered(lambda x: x.email and value in x.email)
           recs = []
        return [('id', 'in', [x.id for x in recs])]

