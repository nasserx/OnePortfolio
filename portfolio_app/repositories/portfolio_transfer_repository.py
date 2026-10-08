"""Transfer retrieval scopes BOTH endpoints to the requesting owner."""

from sqlalchemy import or_
from sqlalchemy.orm import aliased
from portfolio_app.models import Portfolio, PortfolioTransfer
from portfolio_app.repositories.base import BaseRepository


class PortfolioTransferRepository(BaseRepository):
    def __init__(self, model, db, user_id=None):
        super().__init__(model, db)
        self.user_id = user_id

    def _query(self):
        query = self.model.query
        if self.user_id is not None:
            source, destination = aliased(Portfolio), aliased(Portfolio)
            query = query.join(source, self.model.source_portfolio_id == source.id).join(
                destination, self.model.destination_portfolio_id == destination.id,
            ).filter(source.user_id == self.user_id, destination.user_id == self.user_id)
        return query

    def get_by_id(self, identifier):
        return self._query().filter(self.model.id == identifier).first()

    def get_by_portfolio_ids(self, identifiers):
        return self._query().filter(or_(self.model.source_portfolio_id.in_(identifiers),
                                       self.model.destination_portfolio_id.in_(identifiers))).order_by(self.model.id).all()
