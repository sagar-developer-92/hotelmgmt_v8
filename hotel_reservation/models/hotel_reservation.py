# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2012-Today Serpent Consulting Services Pvt. Ltd. (<http://www.serpentcs.com>)
#    Copyright (C) 2004 OpenERP SA (<http://www.openerp.com>)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>
#
##############################################################################
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.exceptions import except_orm, Warning
from dateutil.relativedelta import relativedelta
from openerp import models,fields,api,_
import datetime
import time


class hotel_folio(models.Model):

    _inherit = 'hotel.folio'
    _order = 'reservation_id desc'

    reservation_id = fields.Many2one(comodel_name='hotel.reservation',string='Reservation Id')

class hotel_reservation(models.Model):

    _name = "hotel.reservation"
    _rec_name = "reservation_no"
    _description = "Reservation"
    _order = 'reservation_no desc'
    _inherit = ['mail.thread']

    reservation_no = fields.Char('Reservation No', size=64,readonly=True, default=lambda obj: obj.env['ir.sequence'].get('hotel.reservation'))
    date_order = fields.Datetime('Date Ordered', required=True, readonly=True, states={'draft':[('readonly', False)]},default=lambda *a: time.strftime('%Y-%m-%d %H:%M:%S'))
    warehouse_id = fields.Many2one('stock.warehouse','Hotel', readonly=True, required=True, default = 1, states={'draft':[('readonly', False)]})
    partner_id = fields.Many2one('res.partner','Guest Name' ,readonly=True, required=True, states={'draft':[('readonly', False)]})
    pricelist_id = fields.Many2one('product.pricelist','Scheme' ,required=True, readonly=True, states={'draft':[('readonly', False)]}, help="Pricelist for current reservation. ")
    partner_invoice_id = fields.Many2one('res.partner','Invoice Address' ,readonly=True, states={'draft':[('readonly', False)]}, help="Invoice address for current reservation. ")
    partner_order_id = fields.Many2one('res.partner','Ordering Contact',readonly=True, states={'draft':[('readonly', False)]}, help="The name and address of the contact that requested the order or quotation.")
    partner_shipping_id = fields.Many2one('res.partner','Delivery Address' ,readonly=True, states={'draft':[('readonly', False)]}, help="Delivery address for current reservation. ")
    checkin = fields.Datetime('Expected-Date-Arrival', required=True, readonly=True, states={'draft':[('readonly', False)]})
    checkout = fields.Datetime('Expected-Date-Departure', required=True, readonly=True, states={'draft':[('readonly', False)]})
    adults = fields.Integer('Adults', size=64, readonly=True, states={'draft':[('readonly', False)]}, help='List of adults there in guest list. ')
    children = fields.Integer('Children', size=64, readonly=True, states={'draft':[('readonly', False)]}, help='Number of children there in guest list. ')
    reservation_line = fields.One2many('hotel_reservation.line','line_id','Reservation Line',help='Hotel room reservation details. ')
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm'), ('cancel', 'Cancel'), ('done', 'Done')], 'State', readonly=True,default=lambda *a: 'draft')
    folio_id = fields.Many2many('hotel.folio','hotel_folio_reservation_rel','order_id','invoice_id',string='Folio')
    dummy = fields.Datetime('Dummy')

    @api.onchange('date_order','checkin')
    def on_change_checkin(self):
        '''
        When you change date_order or checkin it will check whether 
        Checkin date should be greater than the current date
        -------------------------------------------------------------
        @param self : object pointer
        @return : raise warning depending on the validation
        '''
        checkin_date=time.strftime('%Y-%m-%d %H:%M:%S')
        if self.date_order and self.checkin:  
            if self.checkin < self.date_order:
                raise except_orm(_('Warning'),_('Checkin date should be greater than the current date.'))


    @api.onchange('checkout','checkin')
    def on_change_checkout(self):
      '''
      When you change checkout or checkin it will check whether 
      Checkout date should be greater than Checkin date 
      and update dummy field
      -------------------------------------------------------------
      @param self : object pointer
      @return : raise warning depending on the validation
      '''
      checkout_date=time.strftime('%Y-%m-%d %H:%M:%S')
      checkin_date=time.strftime('%Y-%m-%d %H:%M:%S')
      res = {}
      if not (checkout_date and checkin_date):
            return {'value':{}}
      if self.checkout and self.checkin:
          if self.checkout < self.checkin:
                    raise except_orm(_('Warning'),_('Checkout date should be greater than Checkin date.'))
      delta = datetime.timedelta(days=1)
      addDays = datetime.datetime(*time.strptime(checkout_date, '%Y-%m-%d %H:%M:%S')[:5]) + delta
      self.dummy = addDays.strftime('%Y-%m-%d %H:%M:%S')


    @api.onchange('partner_id')
    def onchange_partner_id(self):
        '''
        When you change partner_id it will update the partner_invoice_id,
        partner_shipping_id and pricelist_id of the hotel reservation as well
        ----------------------------------------------------------------------
        @param self : object pointer
        '''
        if not self.partner_id:
            self.partner_invoice_id = False
            self.partner_shipping_id=False 
            self.partner_order_id=False
        else:
            partner_lst = [self.partner_id.id]
            addr = self.partner_id.address_get(['delivery', 'invoice', 'contact'])
            self.partner_invoice_id = addr['invoice']
            self.partner_order_id = addr['contact'] 
            self.partner_shipping_id = addr['delivery']
            self.pricelist_id=self.partner_id.property_product_pricelist.id

    @api.multi
    def confirmed_reservation(self):
        """
        This method create a new recordset for hotel room reservation line
        -------------------------------------------------------------------
        @param self: The object pointer
        @return: new record set for hotel room reservation line.
        """
        reservation_line_obj = self.env['hotel.room.reservation.line']
        for reservation in self:
            self._cr.execute("select count(*) from hotel_reservation as hr " \
                        "inner join hotel_reservation_line as hrl on hrl.line_id = hr.id " \
                        "inner join hotel_reservation_line_room_rel as hrlrr on hrlrr.room_id = hrl.id " \
                        "where (checkin,checkout) overlaps ( timestamp %s , timestamp %s ) " \
                        "and hr.id <> cast(%s as integer) " \
                        "and hr.state = 'confirm' " \
                        "and hrlrr.hotel_reservation_line_id in (" \
                        "select hrlrr.hotel_reservation_line_id from hotel_reservation as hr " \
                        "inner join hotel_reservation_line as hrl on hrl.line_id = hr.id " \
                        "inner join hotel_reservation_line_room_rel as hrlrr on hrlrr.room_id = hrl.id " \
                        "where hr.id = cast(%s as integer) )" \
                        , (reservation.checkin, reservation.checkout, str(reservation.id), str(reservation.id)))
            res = self._cr.fetchone()
            roomcount = res and res[0] or 0.0
            if roomcount:
                raise except_orm(_('Warning'), _('You tried to confirm reservation with room those already reserved in this reservation period'))
            if len(reservation.reservation_line) == 0:
                raise except_orm(_('Warning'), _('Please select room to confirm reservation'))
            else:
                self.write({'state':'confirm'})
                for line_id in reservation.reservation_line:
                    line_id = line_id.reserve
                    for room_id in line_id:
                        vals = {
                            'room_id': room_id.id,
                            'check_in': reservation.checkin,
                            'check_out': reservation.checkout,
                            'state': 'assigned',
                            'reservation_id': reservation.id,
                        }
                        reservation_line_obj.create(vals)
                reservation.send_my_maill()
        return True

    @api.multi
    def send_my_maill(self):
        """Generates a new mail message for the Reservation template and schedules it,
           for delivery through the ``mail`` module's scheduler.
           @param self: The object pointer
        """
        template_id = self.env.ref('hotel_reservation.email_template_hotel_reservation', False)
        if template_id.id:
            for user in self:
                if not user.partner_id.email:
                    raise except_orm(("Cannot send email: user has no email address."), user.partner_id.name)
                myobj = self.env['email.template'].browse(template_id.id)
                myobj.send_mail(user.id, force_send=True, raise_exception=True)
            return True 


    @api.multi
    def _create_folio(self):
        """
        This method is for create new hotel folio.
        -----------------------------------------
        @param self: The object pointer
        @return: new record set for hotel folio.
        """
        hotel_folio_obj = self.env['hotel.folio']
        folio_line_obj = self.env['hotel.folio.line']
        room_obj = self.env['hotel.room']
        for reservation in self:
            folio_lines = []
            checkin_date, checkout_date = reservation['checkin'], reservation['checkout']
            if not self.checkin < self.checkout:
                raise except_orm(_('Error'), _('Invalid values in reservation.\nCheckout date should be greater than the Checkin date.'))
            duration_vals = self.onchange_check_dates(checkin_date=checkin_date, checkout_date=checkout_date, duration=False)
            duration = duration_vals.get('duration') or 0.0
            folio_vals = {
                'date_order':reservation.date_order,
                'warehouse_id':reservation.warehouse_id.id,
                'partner_id':reservation.partner_id.id,
                'pricelist_id':reservation.pricelist_id.id,
                'partner_invoice_id':reservation.partner_invoice_id.id,
                'partner_shipping_id':reservation.partner_shipping_id.id,
                'checkin_date': reservation.checkin,
                'checkout_date': reservation.checkout,
                'duration': duration,
                'reservation_id': reservation.id,
                'service_lines':reservation['folio_id']
            }
            for line in reservation.reservation_line:
                for r in line.reserve:
                    folio_lines.append((0, 0, {
                        'checkin_date': checkin_date,
                        'checkout_date': checkout_date,
                        'product_id': r.product_id and r.product_id.id,
                        'name': reservation['reservation_no'],
                        'product_uom': r['uom_id'].id,
                        'price_unit': r['lst_price'],
                        'product_uom_qty': (datetime.datetime(*time.strptime(reservation['checkout'], '%Y-%m-%d %H:%M:%S')[:5]) - datetime.datetime(*time.strptime(reservation['checkin'], '%Y-%m-%d %H:%M:%S')[:5])).days
                    }))
                    res_obj = room_obj.browse([r.id]) 
                    res_obj.write({'status': 'occupied'})
            folio_vals.update({'room_lines': folio_lines})
            folio = hotel_folio_obj.create(folio_vals)
            self._cr.execute('insert into hotel_folio_reservation_rel (order_id, invoice_id) values (%s,%s)', (reservation.id, folio.id))
            reservation.write({'state': 'done'})
        return True


    @api.multi
    def onchange_check_dates(self,checkin_date=False, checkout_date=False, duration=False):
        '''
        This mathod gives the duration between check in checkout if customer will leave only for some
        hour it would be considers as a whole day. If customer will checkin checkout for more or equal
        hours , which configured in company as additional hours than it would be consider as full days
        ---------------------------------------------------------------------------------------------
        @param self : object pointer
        @return : Duration and checkout_date
        '''
        value = {}
        company_obj = self.env['res.company']
        configured_addition_hours = 0
        company_ids = company_obj.search([])
        if company_ids.ids:
            configured_addition_hours = company_ids[0].additional_hours
        duration = 0 
        if checkin_date and checkout_date:
            chkin_dt = datetime.datetime.strptime(checkin_date, '%Y-%m-%d %H:%M:%S')
            chkout_dt = datetime.datetime.strptime(checkout_date, '%Y-%m-%d %H:%M:%S')
            dur = chkout_dt - chkin_dt
            duration = dur.days
            if configured_addition_hours > 0:
                additional_hours = abs((dur.seconds / 60) / 60)
                if additional_hours >= configured_addition_hours:
                    duration += 1
        value.update({'duration':duration})
        return value


class hotel_reservation_line(models.Model):

    _name = "hotel_reservation.line"
    _description = "Reservation Line"

    name = fields.Char('Name', size=64)
    line_id = fields.Many2one('hotel.reservation')
    reserve = fields.Many2many('hotel.room','hotel_reservation_line_room_rel','room_id','hotel_reservation_line_id', domain="[('isroom','=',True),('categ_id','=',categ_id)]")
    categ_id =  fields.Many2one('product.category','Room Type' ,domain="[('isroomtype','=',True)]", change_default=True)

    @api.onchange('categ_id')
    def on_change_categ(self):
        '''
        When you change categ_id it check checkin and checkout are filled or not 
        if not then raise warning 
        ------------------------------------------------------------------------
        @param self : object pointer
        '''
        hotel_room_obj = self.env['hotel.room']
        hotel_room_ids = hotel_room_obj.search([('categ_id', '=',self.categ_id.id)])
        assigned = False
        room_ids = []
        if not self.line_id.checkin:
            raise except_orm(_('Warning'),_('Before choosing a room,\n You have to select a Check in date or a Check out date in the reservation form.'))
        for room in hotel_room_ids:
            assigned = False
            for line in room.room_reservation_line_ids:
                if line.check_in >= self.line_id.checkin and line.check_in <= self.line_id.checkout or line.check_out <= self.line_id.checkout and line.check_out >=self.line_id.checkin:
                    assigned = True
            if not assigned:
                room_ids.append(room.id)
        domain = {'reserve': [('id', 'in', room_ids)]}
        return {'domain': domain}


class hotel_room_reservation_line(models.Model):

    _name = 'hotel.room.reservation.line'
    _description = 'Hotel Room Reservation'
    _rec_name = 'room_id'

    room_id = fields.Many2one(comodel_name='hotel.room',string='Room id')
    check_in = fields.Datetime('Check In Date', required=True)
    check_out = fields.Datetime('Check Out Date', required=True)
    state = fields.Selection([('assigned', 'Assigned'), ('unassigned', 'Unassigned')], 'Room Status')
    reservation_id = fields.Many2one('hotel.reservation',string='Reservation')
     
hotel_room_reservation_line()

class hotel_room(models.Model):

    _inherit = 'hotel.room'
    _description = 'Hotel Room'

    room_reservation_line_ids = fields.One2many('hotel.room.reservation.line','room_id',string='Room Reservation Line')

    @api.model
    def cron_room_line(self):
        """
        This method is for scheduler
        every 1min scheduler will call this method and check Status of room is occupied or available
        --------------------------------------------------------------------------------------------
        @param self: The object pointer
        @return: update status of hotel room reservation line
        """
        reservation_line_obj = self.env['hotel.room.reservation.line']
        now = datetime.datetime.now()
        curr_date = now.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        for room in self.search([]):
            reservation_line_ids = [reservation_line.ids for reservation_line in room.room_reservation_line_ids]
            reservation_line_ids = reservation_line_obj.search([('id', 'in', reservation_line_ids),('check_in', '<=', curr_date), ('check_out', '>=', curr_date)])
            if reservation_line_ids.ids:
                status = {'status': 'occupied'}
            else:
                status = {'status': 'available'}
            room.write(status)
        return True

class room_reservation_summary(models.Model):

     _name = 'room.reservation.summary'
     _description = 'Room reservation summary'

     date_from = fields.Datetime('Date From')
     date_to = fields.Datetime('Date To')
     summary_header = fields.Text('Summary Header')
     room_summary = fields.Text('Room Summary')


     @api.model
     def default_get(self, fields):
        """ 
        To get default values for the object.
        @param self: The object pointer.
        @param fields: List of fields for which we want default values 
        @return: A dictionary which of fields with values. 
        """
        if self._context is None:
             self._context = {}
        res = super(room_reservation_summary, self).default_get(fields)
        if self.date_from == False and self.date_to == False:
            date_today = datetime.datetime.today()
            first_day = datetime.datetime(date_today.year, date_today.month, 1, 0, 0, 0)
            first_temp_day = first_day + relativedelta(months = 1)
            last_temp_day = first_temp_day - relativedelta(days=1)
            last_day = datetime.datetime(last_temp_day.year, last_temp_day.month, last_temp_day.day, 23, 59, 59)
            date_froms = first_day.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            date_ends = last_day.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            res.update({'date_from': date_froms , 'date_to':date_ends})
        return res

     @api.multi
     def room_reservation(self):
         '''
         @param self : object pointer
         '''
         mod_obj = self.env['ir.model.data']
         if self._context is None:
             self._context = {}
         model_data_ids = mod_obj.search([('model', '=', 'ir.ui.view'), ('name', '=', 'view_hotel_reservation_form')])
         resource_id = model_data_ids.read(fields=['res_id'])[0]['res_id']
         return {
             'name': _('Reconcile Write-Off'),
             'context': self._context,
             'view_type': 'form',
             'view_mode': 'form',
             'res_model': 'hotel.reservation',
             'views': [(resource_id, 'form')],
             'type': 'ir.actions.act_window',
             'target': 'new',
         }


     @api.onchange('date_from', 'date_to')
     def get_room_summary(self):
         '''
         @param self : object pointer
         '''
         res = {}
         all_detail = []
         room_obj = self.env['hotel.room']
         reservation_line_obj = self.env['hotel.room.reservation.line']
         date_range_list = []
         main_header = []
         summary_header_list = ['Rooms']
         if self.date_from and self.date_to:
             if self.date_from > self.date_to:
                 raise except_orm(_('User Error!'), _('Please Check Time period Date From can\'t be greater than Date To !'))
             d_frm_obj = datetime.datetime.strptime(self.date_from, DEFAULT_SERVER_DATETIME_FORMAT)
             d_to_obj = datetime.datetime.strptime(self.date_to, DEFAULT_SERVER_DATETIME_FORMAT)
             temp_date = d_frm_obj
             while(temp_date <= d_to_obj):
                 val = ''
                 val = str(temp_date.strftime("%a")) + ' ' + str(temp_date.strftime("%b")) + ' ' + str(temp_date.strftime("%d"))
                 summary_header_list.append(val)
                 date_range_list.append(temp_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT))
                 temp_date = temp_date + datetime.timedelta(days=1)
             all_detail.append(summary_header_list)
             room_ids = room_obj.search([])
             all_room_detail = []
             for room in room_ids:
                 room_detail = {}
                 room_list_stats = []
                 room_detail.update({'name':room.name or ''})
                 if not room.room_reservation_line_ids:
                     for chk_date in date_range_list:
                         room_list_stats.append({'state':'Free', 'date':chk_date})
                 else:
                     for chk_date in date_range_list:
                         for room_res_line in room.room_reservation_line_ids:
                             reservation_line_ids = [i.ids for i in room.room_reservation_line_ids]
                             reservation_line_ids = reservation_line_obj.search([('id', 'in', reservation_line_ids), ('check_in', '<=', chk_date), ('check_out', '>=', chk_date)])
                             if reservation_line_ids:
                                 room_list_stats.append({'state':'Reserved', 'date':chk_date, 'room_id':room.id})
                                 break
                             else:
                                 room_list_stats.append({'state':'Free', 'date':chk_date, 'room_id':room.id})
                                 break
                 room_detail.update({'value':room_list_stats})
                 all_room_detail.append(room_detail)
             main_header.append({'header':summary_header_list})
             self.summary_header = str(main_header)
             self.room_summary = str(all_room_detail)
         return res
 
class quick_room_reservation(models.TransientModel):
     _name = 'quick.room.reservation'
     _description = 'Quick Room Reservation'

     partner_id = fields.Many2one('res.partner', string="Customer", required=True)
     check_in = fields.Datetime('Check In', required=True)
     check_out = fields.Datetime('Check Out', required=True)
     room_id = fields.Many2one('hotel.room', 'Room', required=True)
     warehouse_id = fields.Many2one('stock.warehouse', 'Hotel', required=True)
     pricelist_id = fields.Many2one('product.pricelist', 'pricelist', required=True)
     partner_invoice_id = fields.Many2one('res.partner','Invoice Address' ,required=True)
     partner_order_id = fields.Many2one('res.partner','Ordering Contact', required=True)
     partner_shipping_id = fields.Many2one('res.partner','Delivery Address' ,required=True)

     @api.onchange('check_out','check_in')
     def on_change_check_out(self):
          '''
          When you change checkout or checkin it will check whether 
          Checkout date should be greater than Checkin date 
          and update dummy field
          -------------------------------------------------------------
          @param self : object pointer
          @return : raise warning depending on the validation
          '''
          if self.check_out and self.check_in:
              if self.check_out < self.check_in:
                  raise except_orm(_('Warning'),_('Checkout date should be greater than Checkin date.'))


     @api.onchange('partner_id')
     def onchange_partner_id_res(self):
        '''
        When you change partner_id it will update the partner_invoice_id,
        partner_shipping_id and pricelist_id of the hotel reservation as well
        ----------------------------------------------------------------------
        @param self : object pointer
        '''
        if not self.partner_id:
            self.partner_invoice_id = False
            self.partner_shipping_id=False 
            self.partner_order_id=False
        else:
            addr = self.partner_id.address_get(['delivery', 'invoice', 'contact'])
            self.partner_invoice_id = addr['invoice']
            self.partner_order_id = addr['contact'] 
            self.partner_shipping_id = addr['delivery']
            self.pricelist_id=self.partner_id.property_product_pricelist.id

     @api.model
     def default_get(self, fields):
         """ 
         To get default values for the object.
         @param self: The object pointer.
         @param fields: List of fields for which we want default values 
         @return: A dictionary which of fields with values. 
         """ 
         if self._context is None:
             self._context = {}
         res = super(quick_room_reservation, self).default_get(fields)
         if self._context:
             keys = self._context.keys()
             if 'date' in keys:
                 res.update({'check_in': self._context['date']})
             if 'room_id' in keys:
                 roomid = self._context['room_id']
                 res.update({'room_id': int(roomid)})
         return res

     @api.multi
     def room_reserve(self):
         """
         This method create a new record for hotel.reservation
         -----------------------------------------------------
         @param self: The object pointer
         @return: new record set for hotel reservation.
         """
         hotel_res_obj = self.env['hotel.reservation']
         for room_resv in self:
             hotel_res_obj.create({
                          'partner_id':room_resv.partner_id.id,
                          'partner_invoice_id':room_resv.partner_invoice_id.id,
                          'partner_order_id':room_resv.partner_order_id.id,
                          'partner_shipping_id':room_resv.partner_shipping_id.id,
                          'checkin':room_resv.check_in,
                          'checkout':room_resv.check_out,
                          'warehouse_id':room_resv.warehouse_id.id,
                          'pricelist_id':room_resv.pricelist_id.id,
                          'reservation_line':[(0, 0, {
                          'reserve': [(6, 0, [room_resv.room_id.id])],
                          'name':room_resv.room_id and room_resv.room_id.name or ''})]
                         })
         return True

## vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
